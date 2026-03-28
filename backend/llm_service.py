import os
import json
import logging
from enum import Enum
from pathlib import Path
from typing import Type, Any, no_type_check, cast
from pydantic import BaseModel, ValidationError
from tenacity import retry, stop_after_attempt, wait_fixed
from fastapi import HTTPException
from dotenv import load_dotenv
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from openai import OpenAI

logger = logging.getLogger("careerlens.json_repair")

try:
    from backend import json_repair
except ImportError:
    try:
        import json_repair
    except ImportError:
        from . import json_repair # type: ignore

load_dotenv()

# Raised when the user's BYOK key is invalid/expired/out of quota
class BYOKKeyError(Exception):
    pass

def prepare_schema_for_gemini(schema: Any, full_schema: dict) -> Any:
    """Recursively inlines $ref pointers and STRIPS all non-Gemini keywords (title, description, default, etc)."""
    if not isinstance(schema, dict):
        if isinstance(schema, list):
            return [prepare_schema_for_gemini(item, full_schema) for item in schema]
        return schema

    # 1. Resolve $ref if present
    if "$ref" in schema:
        ref_path = schema["$ref"].split("/")
        if len(ref_path) == 3 and (ref_path[1] == "$defs" or ref_path[1] == "definitions"):
            ref_key = ref_path[2]
            referred_obj = full_schema.get("$defs", {}).get(ref_key, {}) or full_schema.get("definitions", {}).get(ref_key, {})
            return prepare_schema_for_gemini(referred_obj, full_schema)
            
    # 2. Handle anyOf (from Optional values)
    if "anyOf" in schema:
        primary = [p for p in schema["anyOf"] if p.get("type") != "null"]
        if primary:
            return prepare_schema_for_gemini(primary[0], full_schema)

    # 3. Strict Whitelist
    WHITELIST = {'type', 'properties', 'items', 'required', 'enum'}
    cleaned = {}
    for k, v in schema.items():
        if k in WHITELIST:
            if k == 'properties' and isinstance(v, dict):
                cleaned[k] = { 
                    prop_name: prepare_schema_for_gemini(prop_val, full_schema) 
                    for prop_name, prop_val in v.items() 
                }
            else:
                cleaned[k] = prepare_schema_for_gemini(v, full_schema)
    return cleaned

def prepare_schema_for_local(schema: Any, full_schema: dict) -> Any:
    """Keeps types, properties, items, required, enum, but strips titles/descriptions for local models."""
    if not isinstance(schema, dict):
        if isinstance(schema, list):
            return [prepare_schema_for_local(item, full_schema) for item in schema]
        return schema

    if "$ref" in schema:
        ref_path = schema["$ref"].split("/")
        if len(ref_path) == 3 and (ref_path[1] == "$defs" or ref_path[1] == "definitions"):
            ref_key = ref_path[2]
            referred_obj = full_schema.get("$defs", {}).get(ref_key, {}) or full_schema.get("definitions", {}).get(ref_key, {})
            return prepare_schema_for_local(referred_obj, full_schema)

    if "anyOf" in schema:
        primary = [p for p in schema["anyOf"] if p.get("type") != "null"]
        if primary:
            return prepare_schema_for_local(primary[0], full_schema)

    WHITELIST = {'type', 'properties', 'items', 'required', 'enum'}
    cleaned: dict[str, Any] = {}
    for k, v in schema.items():
        if k in WHITELIST:
            if k == 'properties' and isinstance(v, dict):
                cleaned[k] = {pk: prepare_schema_for_local(pv, full_schema) for pk, pv in v.items()}
            else:
                cleaned[k] = prepare_schema_for_local(v, full_schema)
    
    # CRITICAL: Always provide a 'type' to local models to stop them from returning objects for text fields
    if not cleaned.get('type') and not cleaned.get('properties') and not cleaned.get('items'):
        cleaned['type'] = 'string'

    return cleaned

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
        """Verifies API key, quota, and Generative Language API status."""
        if not self.api_key or self.api_key == "REPLACE_WITH_YOUR_KEY":
            return "API Not Configured"
            
        try:
            response = self.model.generate_content("Say OK", generation_config={"max_output_tokens": 5})
            if response.candidates:
                return "API Connected"
            return "Key Works (No Response)"
        except google_exceptions.ResourceExhausted:
            return "Out of Credits"
        except google_exceptions.Unauthenticated:
            return "Invalid API Key"
        except Exception as e:
            msg = str(e).lower()
            if "quota" in msg:
                return "Out of Credits"
            if "api key not valid" in msg or "invalid api key" in msg:
                return "Invalid API Key"
            return f"Error: {str(e)}"

    def generate_json(self, system_prompt: str, user_prompt: str, schema_json: dict | None = None) -> str:
        try:
            full_prompt = f"{system_prompt}\n\n{user_prompt}"
            generation_config: dict = {"response_mime_type": "application/json"}
            if schema_json:
                generation_config["response_schema"] = schema_json

            response = self.model.generate_content(
                full_prompt,
                generation_config=generation_config
            )
            
            if not response.candidates:
                raise BYOKKeyError("Gemini failed to generate candidates.")
                
            return response.text
        except Exception as e:
            raise BYOKKeyError(f"Google API Error: {str(e)}")

class LocalLLMClient(LLMClient):
    def __init__(self, base_url: str | None = None):
        api_key = "not-needed"
        model_id = "local-model"
        
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
        try:
            # Short timeout for health check
            self.client.models.list()
            return "Local Connected"
        except Exception as e:
            msg = str(e).lower()
            logger.warning(f"Local Connectivity Check Failed: {msg}")
            if "no models loaded" in msg:
                return "LM Studio: Load Model"
            if "connection refused" in msg or "not found" in msg:
                return "Local Offline"
            return "Local Error"
        
    def generate_json(self, system_prompt: str, user_prompt: str, schema_json: dict | None = None) -> str:
        kwargs: dict = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 4096
        }

        if schema_json:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "CareerData",
                    "strict": False,
                    "schema": schema_json
                }
            }

        try:
            response = self.client.chat.completions.create(
                **kwargs,
                timeout=180
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            if "timeout" in str(e).lower():
                raise HTTPException(status_code=408, detail="Local LLM Timeout")
            raise

class JSONRecoveryRetryError(Exception):
    pass

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
def _generate_with_retry(
    client: LLMClient,
    job_desc: str,
    master_facts: str,
    target_seniority: str,
    schema_model: Type[BaseModel],
    provider: LLMProvider,
    attempt_history: dict,
    system_prompt_extension: str = ""
) -> BaseModel:
    
    attempt_history["attempt"] += 1
    raw_schema = schema_model.model_json_schema()
    
    SENIORITY_MATRIX = {
        "Executive": "DIRECTIVE: Target seniority is EXECUTIVE. Content Weight: 80% Strategy/ROI, 20% Execution. JSON Map: Fill {{REALITY_BADGE}} with 'Strategic Asset.'",
        "Senior": "DIRECTIVE: Target seniority is SENIOR. Content Weight: 50% Technical Expertise, 50% Leadership/Mentoring. JSON Map: Fill {{REALITY_BADGE}} with 'Subject Matter Expert.'",
        "Mid-Level": "DIRECTIVE: Target seniority is MID-LEVEL. Redact all management-level achievements. JSON Map: Fill {{REALITY_BADGE}} with 'Turnkey Professional.'",
        "Junior": "DIRECTIVE: Target seniority is JUNIOR. Strip all management-level achievements. JSON Map: Fill {{REALITY_BADGE}} with 'High-Potential Contributor.'",
        "Entry": "DIRECTIVE: Target seniority is ENTRY/ASSISTANT. JSON Map: Fill {{REALITY_BADGE}} with 'Foundational Asset.'"
    }
    directive = SENIORITY_MATRIX.get(target_seniority, SENIORITY_MATRIX["Mid-Level"])
    
    system_prompt = f"""You are an expert Career Advisor.
{system_prompt_extension}
RULES:
1. Complete JSON for provided schema.
2. No Markdown.
3. Extract Contact Info from Profile.
4. EXACTLY 6 'MATCHES'.
Facts: {master_facts}
--- SENIORITY ---
{directive}
"""
    
    user_prompt = f"Job Description:\n{job_desc}"

    if attempt_history["attempt"] > 1:
        validation_errors = attempt_history.get("last_error", "Invalid JSON format.")
        system_prompt += f"\n\nFIX REQUEST: Last attempt failed:\n{validation_errors}"
    
    if provider == LLMProvider.GOOGLE:
        schema = prepare_schema_for_gemini(raw_schema, raw_schema)
    else:
        schema = prepare_schema_for_local(raw_schema, raw_schema)

    try:
        raw_output = client.generate_json(system_prompt=system_prompt, user_prompt=user_prompt, schema_json=schema)
        # Cleanup
        raw_output = str(raw_output).strip().replace("```json", "").replace("```", "")
            
        try:
            parsed_json = json_repair.try_parse_repaired_json(raw_output)
        except Exception as e:
            attempt_history["last_error"] = f"JSON Parse Error: {str(e)}"
            raise JSONRecoveryRetryError(f"Parse failed: {str(e)}")

        try:
            return schema_model.model_validate(parsed_json)
        except ValidationError as e:
            error_details = [f"Key '{'.'.join([str(l) for l in err['loc']])}': {err['msg']}" for err in e.errors()]
            exact_errors = "\n".join(error_details)
            attempt_history["last_error"] = exact_errors
            raise JSONRecoveryRetryError(f"Validation failed: {exact_errors}")
        
    except Exception as e:
        logger.error(f"Attempt {attempt_history['attempt']} failed: {str(e)}")
        raise

def generate_career_data(
    job_desc: str,
    master_resume: str,
    target_seniority: str = "Mid-Level",
    schema_model: Type[BaseModel] | None = None,
    user_api_key: str | None = None,
    force_local: bool = False,
    system_prompt_extension: str = ""
) -> dict:
    # 1. Determine Provider
    is_lm_link = user_api_key and (user_api_key.startswith("http://") or user_api_key.startswith("https://"))
    has_user_key = bool(user_api_key and user_api_key.strip())
    
    provider = LLMProvider.LOCAL
    if is_lm_link or not has_user_key or force_local:
        provider = LLMProvider.LOCAL
    else:
        provider = LLMProvider.GOOGLE

    # 2. Select Client
    client: LLMClient
    if provider == LLMProvider.GOOGLE:
        client = GoogleLLMClient(user_api_key=user_api_key)
    else:
        client = LocalLLMClient(base_url=user_api_key if is_lm_link else None)

    # 3. Schema
    if not schema_model:
        from .dynamic_parsing import parse_html_to_pydantic
        schema_model = parse_html_to_pydantic()
    
    master_facts = read_master_data()
    
    attempt_history = {"attempt": 0, "last_error": None}
    
    validated_data = _generate_with_retry(
        client=client,
        job_desc=job_desc,
        master_facts=master_facts,
        target_seniority=target_seniority,
        schema_model=schema_model,
        provider=provider,
        attempt_history=attempt_history,
        system_prompt_extension=system_prompt_extension
    )
    
    return validated_data.model_dump()
