from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
import json
import time
import logging
import threading
import jinja2
from pathlib import Path
from collections import defaultdict

from backend.llm_service import generate_career_data, BYOKKeyError, _generate_with_retry
from backend.dynamic_parsing import parse_html_to_pydantic

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("careerlens")

app = FastAPI(title="CareerLens AI API")

# --- API Secret (set via env var or .env) ---
API_SECRET = os.getenv("CL_API_SECRET", "")

# --- Rate Limiter (in-memory, per IP) ---
RATE_LIMIT = int(os.getenv("CL_RATE_LIMIT", "5"))  # max requests per window
RATE_WINDOW = int(os.getenv("CL_RATE_WINDOW", "86400"))  # 24 hours in seconds
_rate_store: dict[str, list[float]] = defaultdict(list)

# --- Single-Request Lock (one generation at a time) ---
_generation_lock = threading.Lock()

def _is_local(ip: str) -> bool:
    """Exempt localhost and Docker-internal IPs from rate limits."""
    return ip.startswith("127.") or ip.startswith("172.") or ip.startswith("10.") or ip.startswith("192.168.") or ip == "::1"

def _is_rate_limited(client_ip: str) -> bool:
    if _is_local(client_ip):
        return False
    now = time.time()
    # Purge old entries outside the window
    _rate_store[client_ip] = [t for t in _rate_store[client_ip] if now - t < RATE_WINDOW]
    if len(_rate_store[client_ip]) >= RATE_LIMIT:
        return True
    _rate_store[client_ip].append(now)
    return False

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class GenerateRequest(BaseModel):
    job_description: str
    master_resume: str = ""
    user_api_key: str | None = None
    target_seniority: str = "Mid-Level"
    force_local: bool = False

class VerifyRequest(BaseModel):
    user_api_key: str | None = None

@app.get("/api/v1/health")
def health_check():
    provider = os.getenv("LLM_PROVIDER", "auto")
    status = "Not Connected"
    try:
        from backend.llm_service import GoogleLLMClient
        # This will check the server-side GOOGLE_API_KEY
        g_client = GoogleLLMClient()
        status = g_client.verify_connectivity()
    except Exception as e:
        status = f"Status Error: {str(e)}"
        
    return {"status": "ok", "api_status": status, "active_provider": provider}

@app.post("/api/v1/verify-key")
def verify_key_endpoint(req: VerifyRequest):
    from backend.llm_service import GoogleLLMClient, LocalLLMClient
    
    if req.user_api_key and req.user_api_key.startswith(("http://", "https://")):
        client = LocalLLMClient(base_url=req.user_api_key)
        status = client.verify_connectivity()
        return {"status": status, "type": "local"}
    
    try:
        client = GoogleLLMClient(user_api_key=req.user_api_key)
        status = client.verify_connectivity()
        return {"status": status, "type": "google"}
    except Exception as e:
        return {"status": str(e), "type": "error"}

@app.post("/api/v1/generate", response_class=HTMLResponse)
def generate_endpoint(req: GenerateRequest, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    logger.info(f"Generate request from {client_ip}")

    # --- Gate 1: API Secret Check (skip for local IPs) ---
    if API_SECRET and not _is_local(client_ip):
        provided_key = request.headers.get("X-CL-Key", "")
        if provided_key != API_SECRET:
            logger.warning(f"Rejected request from {client_ip}: invalid API secret")
            raise HTTPException(status_code=403, detail="Invalid API key")

    # --- Gate 2: Rate Limit Check (5 per day per IP) ---
    if _is_rate_limited(client_ip):
        logger.warning(f"Rate limited {client_ip}")
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute.")

    # --- Gate 3: Single-request queue (protect GPU) ---
    acquired = _generation_lock.acquire(timeout=120)  # wait up to 2 min
    if not acquired:
        raise HTTPException(status_code=503, detail="Server busy. Another generation is in progress.")

    try:
        return _do_generate(req, client_ip)
    finally:
        _generation_lock.release()

def _do_generate(req: GenerateRequest, client_ip: str):
    template_path = Path(__file__).parent.parent / "Template4.html"
    try:
        html_content = template_path.read_text(encoding="utf-8")
        DynamicCareerData = parse_html_to_pydantic(html_content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read template or build schema: {e}")

    if not req.job_description:
        raise HTTPException(status_code=400, detail="Missing Job Description")
    
    # master_resume is now optional; if blank, llm_service falls back to personal MD file

    byok_error_reason: str | None = None

    # --- Strategy: Blueprint-Guided Generation ---
    # We extract all expected keys for our Dynamic Model and pass them to the LLM.
    # We use descriptive values like "(text)" instead of "..." to prevent LLM loops.
    schema_info = DynamicCareerData.model_json_schema().get("properties", {})
    schema_blueprint = json.dumps({k: "(generate detailed text here)" for k in schema_info}, indent=2)
    
    blueprint_prompt = (
        f"IMPORTANT: Strictly adhere to this JSON structure blueprint:\n"
        f"```json\n{schema_blueprint}\n```\n"
        "Rules:\n"
        "1. Output valid JSON ONLY.\n"
        "2. NO Conversational filler.\n"
        "3. NO Placeholders: Do NOT return literally '{{VAR}}' or '(text)'. Replace with actual content.\n"
        "4. Exact Keys: Ensure ALL keys from the blueprint are present.\n"
    )

    try:
        from backend.llm_service import generate_career_data
        
        # We always call generate_career_data, it handles all routing (Gemini vs Local) internally
        data_model_dict = generate_career_data(
            job_desc=req.job_description,
            master_resume=req.master_resume,
            target_seniority=req.target_seniority,
            schema_model=DynamicCareerData,
            user_api_key=req.user_api_key,
            force_local=req.force_local,
            system_prompt_extension=blueprint_prompt
        )
            
    except BYOKKeyError as e_api:
        # IMPORTANT: If the API failed, we RAISE immediately.
        # This gives the user instant feedback (2 seconds vs 70 seconds).
        # They can choose to "Try Local" manually in the UI.
        raise HTTPException(
            status_code=403,
            detail=str(e_api),
            headers={"X-Technical-Details": str(e_api)}
        )
    except Exception as e:
        # Catch other errors (Local failing, or fatal system errors)
        logger.error(f"[Generation] Fatal error for {client_ip}: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Generation Failed: {str(e)}",
            headers={"X-Technical-Details": str(e)}
        )

    data_dict = data_model_dict
    try:
        template = jinja2.Template(html_content)
        rendered_html = template.render(**data_dict)
    except Exception as e:
        logger.error(f"Jinja2 Render Error: {e}")
        rendered_html = html_content
        for key, value in data_dict.items():
            placeholder = f"{{{{{key}}}}}"
            rendered_html = rendered_html.replace(placeholder, str(value) if value is not None else "")

    logger.info(f"Successfully generated resume for {client_ip}")

    headers = {}
    if byok_error_reason:
        # Signal to Flutter: show blocking dialog with this reason, result is from Local fallback
        headers["X-BYOK-Error"] = byok_error_reason

    return HTMLResponse(content=rendered_html, status_code=200, headers=headers)

static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
