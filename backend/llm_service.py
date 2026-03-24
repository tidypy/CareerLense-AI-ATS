import os
import json
from enum import Enum
from pathlib import Path
from typing import Type
from pydantic import BaseModel, ValidationError
from tenacity import retry, stop_after_attempt, wait_fixed
from fastapi import HTTPException
from dotenv import load_dotenv
import google.generativeai as genai
from openai import OpenAI

load_dotenv()

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
    def generate_json(self, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError

class GoogleLLMClient(LLMClient):
    def __init__(self, user_api_key: str = None):
        self.api_key = user_api_key if user_api_key else os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY is missing and no BYOK provided")
        
        project_id = os.getenv("GCP_PROJECT_ID")
        if project_id:
            os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
            
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel('gemini-2.5-flash', generation_config={"response_mime_type": "application/json"})

    def generate_json(self, system_prompt: str, user_prompt: str) -> str:
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        response = self.model.generate_content(full_prompt)
        return response.text

class LocalLLMClient(LLMClient):
    def __init__(self, base_url: str = None):
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
        
    def generate_json(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model_id,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=24000
        )
        return response.choices[0].message.content


class JSONRecoveryRetryError(Exception):
    pass

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
def run_generation_with_retry(
        client: LLMClient,
        job_description: str,
        master_resume: str,
        schema_model: Type[BaseModel],
        attempt_history: dict) -> BaseModel:
    
    attempt_history["attempt"] += 1
    
    master_facts = read_master_data()
    model_schema_json = json.dumps(schema_model.model_json_schema(), indent=2)
    
    # Problem 5: Token Budget Management
    # If this is a retry, do not blindly append the massive user resume.
    if attempt_history["attempt"] == 1:
        system_prompt = f"""You are an expert Career Advisor and ATS Optimizer.
You MUST output a pure, complete JSON object. DO NOT SKIP SECTIONS. DO NOT TRUNCATE.
The JSON structure must STRICTLY adhere to this schema definition:
{model_schema_json}

IMPORTANT RULES:
1. For array fields (like 'MATCHES', 'EXPERIENCES', 'TECHNOLOGIES'), you MUST output a proper JSON Array of objects (e.g. [{{"TITLE": "..."}}]). DO NOT hallucinate flat keys like 'MATCH_1_TITLE'.
2. Do not include any reasoning blocks, markdown tags, or conversational text. Output purely the JSON object so it parses immediately.

Use the following candidate facts as reference:
{master_facts}
"""
        user_prompt = f"Job Description:\n{job_description}\n\nMaster Profile:\n{master_resume}"
    else:
        # Token Management: Send ONLY strict schema rules alongside specific validation errors.
        validation_errors = attempt_history.get("last_error", "Invalid JSON format.")
        system_prompt = f"""You MUST output a raw JSON object string ONLY. DO NOT TRUNCATE. Your response must strictly validate against the following schema:
{model_schema_json}

IMPORTANT: For array fields, output a proper JSON Array! DO NOT hallucinate flat keys like 'MATCH_1_TITLE'.

Your last attempt failed with the following validation errors. Fix these exact missing or malformed keys:
{validation_errors}
"""
        user_prompt = "Generate the corrected complete JSON incorporating the missing/malformed keys."
    
    try:
        raw_output = client.generate_json(system_prompt, user_prompt)
        
        # Cleanup
        if raw_output.startswith("```json"):
            raw_output = raw_output[7:]
        if raw_output.startswith("```"):
            raw_output = raw_output[3:]
        if raw_output.endswith("```"):
            raw_output = raw_output[:-3]
            
        parsed_json = json.loads(raw_output.strip())
        validated_data = schema_model(**parsed_json)
        return validated_data
        
    except ValidationError as e:
        # Problem 1: Vague Retry Feedback
        # Iterate over e.errors() and capture exact missing/malformed keys
        error_details = []
        for err in e.errors():
            loc = " -> ".join([str(l) for l in err['loc']])
            error_details.append(f"Key '{loc}': {err['msg']}")
        
        exact_errors = "\n".join(error_details)
        print(f"Validation error on attempt {attempt_history['attempt']}:\n{exact_errors}")
        attempt_history["last_error"] = exact_errors
        raise JSONRecoveryRetryError(f"Failed to generate valid JSON: {exact_errors}")
        
    except json.JSONDecodeError as e:
        print(f"JSON Parse error on attempt {attempt_history['attempt']}: {e}")
        attempt_history["last_error"] = f"JSON Decode Error: {str(e)}"
        raise JSONRecoveryRetryError(f"Failed to parse JSON: {str(e)}")
    except Exception as e:
        print(f"API error on attempt {attempt_history['attempt']}: {e}")
        raise


def generate_career_data(job_description: str, master_resume: str, schema_model: Type[BaseModel], user_api_key: str = None) -> BaseModel:
    provider_str = os.getenv("LLM_PROVIDER", "auto").lower()
    
    # Instantiate clients
    google_client = None
    local_client = None
    
    is_lm_link = user_api_key and (user_api_key.startswith("http://") or user_api_key.startswith("https://"))
    
    if is_lm_link:
        provider_str = "local"
        try:
            local_client = LocalLLMClient(base_url=user_api_key)
        except Exception as e:
            print(f"Local Client init failed: {e}")
    else:
        try:
            google_client = GoogleLLMClient(user_api_key=user_api_key)
        except Exception as e:
            print(f"Google Client init failed: {e}")
            
        try:
            local_client = LocalLLMClient()
        except Exception as e:
            print(f"Local Client init failed: {e}")
        
    def try_with_client(client: LLMClient, name: str):
        if not client:
            raise ValueError(f"{name} client is unavailable.")
        print(f"Attempting generation with {name} client...")
        return run_generation_with_retry(client, job_description, master_resume, schema_model, {"attempt": 0})

    # Problem 4: Backup failover logic ("Two-Phase Credit Commit")
    if provider_str == "google":
        return try_with_client(google_client, "Google")
    elif provider_str == "local":
        return try_with_client(local_client, "Local")
    else:
        try:
            return try_with_client(google_client, "Google")
        except Exception as e:
            print(f"Primary Provider (Google) failed 3 times: {e}. Graceful failover to Backup Provider (Local)...")
            try:
                return try_with_client(local_client, "Local")
            except Exception as e_local:
                raise Exception(f"Total Failure. Primary error: {e}. Backup error: {e_local}")
