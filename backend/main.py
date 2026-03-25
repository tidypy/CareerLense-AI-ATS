from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
import jinja2
from pathlib import Path

from backend.llm_service import generate_career_data
from backend.dynamic_parsing import parse_html_to_pydantic

app = FastAPI(title="CareerLens AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class GenerateRequest(BaseModel):
    job_description: str
    master_resume: str
    user_api_key: str | None = None
    target_seniority: str = "Mid-Level"

@app.get("/api/v1/health")
def health_check():
    provider = os.getenv("LLM_PROVIDER", "auto")
    return {"status": "ok", "active_provider": provider}

@app.post("/api/v1/generate", response_class=HTMLResponse)
def generate_endpoint(req: GenerateRequest):
    template_path = Path(__file__).parent.parent / "Template4.html"
    try:
        html_content = template_path.read_text(encoding="utf-8")
        DynamicCareerData = parse_html_to_pydantic(html_content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read template or build schema: {e}")
        
    if not req.job_description or not req.master_resume:
        raise HTTPException(status_code=400, detail="Missing inputs")
        
    data_model = generate_career_data(
        req.job_description, 
        req.master_resume, 
        DynamicCareerData, 
        req.user_api_key, 
        req.target_seniority
    )
        
    data_dict = data_model.model_dump()
    try:
        template = jinja2.Template(html_content)
        html_content = template.render(**data_dict)
    except Exception as e:
        print(f"Jinja2 Render Error: {e}")
        # Fallback to pure string replacement if Jinja fails
        for key, value in data_dict.items():
            placeholder = f"{{{{{key}}}}}"
            html_content = html_content.replace(placeholder, str(value) if value is not None else "")
            
    return html_content

static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
