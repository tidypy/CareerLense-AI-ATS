import os
import json
import logging
import logging
from enum import Enum
from pathlib import Path
from typing import Type, no_type_check, cast
from pydantic import BaseModel, ValidationError
from tenacity import retry, stop_after_attempt, wait_fixed
from fastapi import HTTPException
from dotenv import load_dotenv
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from openai import OpenAI

logger = logging.getLogger("careerlens.json_repair")

try:
    from backend.json_repair import try_parse_repaired_json, repair_json
except ImportError:
    try:
        from .json_repair import try_parse_repaired_json, repair_json
    except ImportError:
        from json_repair import try_parse_repaired_json, repair_json

load_dotenv()

# Raised when the user's BYOK key is invalid/expired/out of quota
class BYOKKeyError(Exception):
    pass

class LLMProvider(str, Enum):
    GOOGLE = "google"
    LOCAL = "local"
    AUTO = "auto"

def read_master_data() -> str:
    master_md_path = Path(__file__).parent.parent / "MasterDataMDfileVER-4.md"
    try:
        if master_md_path.exists():
            return master_md_path.read_text(encoding="utf-8")
        else:
            return "No Master Data provided."
    except Exception as e:
        return f"Error reading Master Data: {str(e)}"

# Provider Abstraction
class LLMClient:
    def generate_json(self, system_prompt: str, user_prompt: str, schema_json: dict | None = None) -> str:
        raise NotImplementedError

class GoogleLLMClient(LLMClient):
    def __init__(self, user_api_key: str | None = None):
        self.api_key = user_api_key if user_api_key else os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY is missing and no BYOK provided")
        
        project_id = os.getenv("GCP_PROJECT_ID")
        if project_id:
            os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
            
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel('gemini-2.5-flash', generation_config={"response_mime_type": "application/json"})

    def verify_connectivity(self) -> str:
        """Verifies API key and quota."""
        try:
            # list_models is a safe way to check connectivity without generating content
            for _ in genai.list_models():
                break
            return "ok"
        except google_exceptions.Unauthenticated:
            return "Invalid API Key"
        except google_exceptions.ResourceExhausted:
            return "Quota Exhausted"
        except Exception as e:
            return f"Error: {str(e)}"

    def generate_json(self, system_prompt: str, user_prompt: str, schema_json: dict | None = None) -> str:
        try:
            full_prompt = f"{system_prompt}\n\n{user_prompt}"
            
            # If schema is provided, we can either update the model config or pass it here.
            # For Gemini, it's often best to set it in the generation_config.
            generation_config: dict = {"response_mime_type": "application/json"}
            if schema_json:
                generation_config["response_schema"] = schema_json

            response = self.model.generate_content(
                full_prompt,
                generation_config=generation_config
            )
            return response.text
        except google_exceptions.InvalidArgument as e:
            raise BYOKKeyError(f"Invalid API key — Google rejected it. Check that your key is correct. ({e.message})") from e
        except google_exceptions.PermissionDenied as e:
            raise BYOKKeyError(f"API key does not have permission. Verify the key is enabled for Gemini. ({e.message})") from e
        except google_exceptions.ResourceExhausted as e:
            raise BYOKKeyError(f"API key quota exhausted — you are out of tokens or have hit a rate limit. ({e.message})") from e
        except google_exceptions.Unauthenticated as e:
            raise BYOKKeyError(f"API key authentication failed. The key may be expired or revoked. ({e.message})") from e

class LocalLLMClient(LLMClient):
    def __init__(self, base_url: str | None = None):
        api_key = "not-needed"
        model_id = "local-model"
        
        # Parse complex LM Studio BYOK: http://url:1234/v1|API_KEY|MODEL_ID
        if base_url and "|" in base_url:
            parts = base_url.split("|")
            base_url = parts[0]
            if len(parts) > 1 and parts[1].strip():
                api_key = parts[1].strip()
            if len(parts) > 2 and parts[2].strip():
                model_id = parts[2].strip()
                
        if not base_url:
            base_url = "http://host.docker.internal:1234/v1"
            
        if not base_url.endswith("/v1"):
            base_url = base_url.rstrip("/") + "/v1"
            
        self.model_id = model_id
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        
    def verify_connectivity(self) -> str:
        """Verifies local server is up."""
        try:
            # Try to list models
            self.client.models.list()
            return "ok"
        except Exception as e:
            return f"Local Server Offline: {str(e)}"
        
    def generate_json(self, system_prompt: str, user_prompt: str, schema_json: dict | None = None) -> str:
        kwargs: dict = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 24000
        }

        # Enable structured output if schema is provided
        if schema_json:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "CareerData",
                    "strict": False,
                    "schema": schema_json
                }
            }

        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""


class JSONRecoveryRetryError(Exception):
    pass

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
def run_generation_with_retry(
        client: LLMClient,
        job_description: str,
        master_resume: str,
        schema_model: Type[BaseModel],
        attempt_history: dict,
        target_seniority: str = "Mid-Level") -> BaseModel:
    
    attempt_history["attempt"] += 1
    
    # Determine source of truth: User Input vs. Local Personal Data
    if master_resume and master_resume.strip():
        master_facts = master_resume.strip()
    else:
        master_facts = read_master_data()

    # Extract the actual dict schema for API consumption
    schema_dict = schema_model.model_json_schema()
    
    SENIORITY_MATRIX = {
        "Executive": """DIRECTIVE: Target seniority is EXECUTIVE.
Title Selection: Prioritize (Exec) variants (e.g., Director, Owner).
Content Weight: 80% Strategy/ROI, 20% Execution.
Achievement Filter: Focus on P&L impact, governance, $250k+ savings, and organizational architecture.
JSON Map: Fill {{REALITY_BADGE}} with "Strategic Asset."
""",
        "Senior": """DIRECTIVE: Target seniority is SENIOR.
Title Selection: Prioritize (Sr) or (Exec) if the role is a "Lead" position.
Content Weight: 50% Technical Expertise, 50% Leadership/Mentoring.
Achievement Filter: Focus on process optimization, systems architecture, and project spearheading.
JSON Map: Fill {{REALITY_BADGE}} with "Subject Matter Expert."
""",
        "Mid-Level": """DIRECTIVE: Target seniority is MID-LEVEL.
Title Selection: STRICT: Pick ONLY (Mid) variants. Redact all "Director," "Owner," and "SBA" prefixes.
Content Weight: 90% Task Execution/Compliance, 10% Oversight.
Achievement Filter: Focus on SOP adherence, daily operations, payroll accuracy, and technical proficiency.
JSON Map: Fill {{REALITY_BADGE}} with "Turnkey Professional."
""",
        "Junior": """DIRECTIVE: Target seniority is JUNIOR.
Title Selection: Pick (Mid) or (Entry) variants. Strip all management-level achievements.
Content Weight: 100% Technical Tasks/Learning.
Achievement Filter: Focus on reliability, documentation, and specific tool utilization.
JSON Map: Fill {{REALITY_BADGE}} with "High-Potential Contributor."
""",
        "Entry": """DIRECTIVE: Target seniority is ENTRY/ASSISTANT.
Title Selection: STRICT: Use (Entry) titles. If unavailable, use (Mid) and downgrade the summary to "Coordinator" or "Support".
Content Weight: 100% Administrative/Manual Support.
Achievement Filter: Focus on attendance, basic workflow completion, and general support tasks.
JSON Map: Fill {{REALITY_BADGE}} with "Foundational Asset."
"""
    }
    directive = SENIORITY_MATRIX.get(target_seniority, SENIORITY_MATRIX["Mid-Level"])
    
    system_prompt = f"""You are an expert Career Advisor and ATS Optimizer.
Your goal is to transform the provided master profile into a highly tailored, ATS-optimized report for the specific job description.

IMPORTANT RULES:
1. Complete JSON: You MUST output a complete, valid JSON object that populates EVERY field in the provided schema. Do not skip or truncate any section.
2. No Markdown: Do NOT use markdown formatting (like **bolding**) inside any JSON string values. Use plain text only.
3. Contact Info: Extract CANDIDATE_NAME, CANDIDATE_LOCATION, CANDIDATE_EMAIL, CANDIDATE_LINKEDIN from the Master Profile. Use "Not Provided" if missing.
4. Structure: You MUST generate EXACTLY 6 objects inside the 'MATCHES' array to complete the UI grid layout.
5. Content: Be specific, quantifiable, and align exactly with the target seniority.

Use the following candidate facts as reference:
{master_facts}

--- CRITICAL SENIORITY DIRECTIVE ---
{directive}
"""
    # Fallback to including the schema in the prompt only if we were NOT doing constrained decoding
    # But here we will always pass the schema dict to the client now.
    
    user_prompt = f"Job Description:\n{job_description}"

    if attempt_history["attempt"] > 1:
        validation_errors = attempt_history.get("last_error", "Invalid JSON format.")
        system_prompt += f"\n\nCRITICAL FIX REQUIRED: Your last attempt failed with validation errors. You MUST fix these:\n{validation_errors}"
    
    try:
        raw_output = client.generate_json(system_prompt, user_prompt, schema_json=schema_dict)
        
        # Cleanup
        raw_output = str(raw_output).strip()
        if raw_output.startswith("```json"):
            raw_output = raw_output.replace("```json", "", 1)
        if raw_output.endswith("```"):
            raw_output = raw_output[:-3]
        if raw_output.startswith("```"):
            raw_output = raw_output.replace("```", "", 1)
            
        # Robust Validation with Repair Attempt
        try:
            parsed_json = try_parse_repaired_json(raw_output)
        except json.JSONDecodeError as e:
            # Check if it was because it's too long
            is_truncated = False
            if len(raw_output) > 20000: # Heuristic
                 is_truncated = True
            
            error_msg = f"JSON Parse error on attempt {attempt_history['attempt']}: {e}"
            if is_truncated:
                error_msg += " (Output appears truncated)"
            
            print(error_msg)
            safe_output = cast(str, str(raw_output))
            print(f"RAW OUTPUT THAT FAILED TO PARSE:\n{safe_output[0:500]}... [TRUNCATED]")
            attempt_history["last_error"] = f"JSON Decode Error: {str(e)}"
            raise JSONRecoveryRetryError(f"Failed to parse JSON: {str(e)}")

        # Type Guard: Ensure schema_model is a class and not an error object
        if not hasattr(schema_model, "model_validate"):
             print(f"ERROR: schema_model is not a valid Pydantic V2 class! Got: {type(schema_model)}")
             raise TypeError(f"Expected a Pydantic V2 model class, got {type(schema_model)}")

        try:
            # Use model_validate (Pydantic V2) for better error reporting
            validated_data = schema_model.model_validate(parsed_json)
            return validated_data
        except ValidationError as e:
            # Problem 1: Vague Retry Feedback
            # Iterate over e.errors() and capture exact missing/malformed keys
            error_details = []
            for err in e.errors():
                loc = " -> ".join([str(l) for l in err['loc']])
                error_details.append(f"Key '{loc}': {err['msg']} (Input Type: {err.get('input_type', 'unknown')})")
            
            exact_errors = "\n".join(error_details)
            print(f"Validation error on attempt {attempt_history['attempt']}:\n{exact_errors}")
            print(f"RAW OUTPUT THAT FAILED VALIDATION:\n{raw_output}")
            attempt_history["last_error"] = exact_errors
            raise JSONRecoveryRetryError(f"Failed to generate valid JSON: {exact_errors}")
        
    except Exception as e:
        print(f"API/System error on attempt {attempt_history['attempt']}: {e}")
        raise


def generate_career_data(
    job_description: str,
    master_resume: str,
    schema_model: Type[BaseModel],
    user_api_key: str | None = None,
    target_seniority: str = "Mid-Level"
) -> BaseModel:
    """
    BYOK Routing Rules:
    - user_api_key is blank/None → go DIRECTLY to Local RTX (TailScale). Skip Google entirely.
    - user_api_key is an http/https URL → treat as LM Studio endpoint, go local.
    - user_api_key has a value (Google key) → try Google first.
        - If BYOKKeyError is raised, re-raise it so main.py can fall back to local
          and set the X-BYOK-Error response header for the frontend dialog.
    """
    is_lm_link = user_api_key and (user_api_key.startswith("http://") or user_api_key.startswith("https://"))
    has_user_key = bool(user_api_key and user_api_key.strip())

    def try_with_client(client: LLMClient, name: str):
        if not client:
            raise ValueError(f"{name} client is unavailable.")
        print(f"[BYOK] Attempting generation with {name} client for seniority '{target_seniority}'...")
        return run_generation_with_retry(client, job_description, master_resume, schema_model, {"attempt": 0}, target_seniority)

    # ── Path A: LM Studio URL provided ──────────────────────────────────────
    if is_lm_link:
        print(f"[BYOK] LM Studio URL detected — routing directly to Local.")
        local_client = LocalLLMClient(base_url=user_api_key)
        return try_with_client(local_client, "Local (LM Studio BYOK)")

    # ── Path B: Blank key — skip Google, go straight to Local RTX ───────────
    if not has_user_key:
        print(f"[BYOK] Key is blank — routing directly to Local RTX (TailScale).")
        local_client = LocalLLMClient()
        return try_with_client(local_client, "Local RTX")

    # ── Path C: Google BYOK key provided — try Google, propagate BYOKKeyError ─
    print(f"[BYOK] User key provided — trying Google first.")
    google_client = GoogleLLMClient(user_api_key=user_api_key)
    # BYOKKeyError is intentionally NOT caught here — let main.py handle it
    # so it can do the local fallback and set the response header.
    return try_with_client(google_client, "Google (BYOK)")
