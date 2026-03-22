import os
import json
from enum import Enum
from pathlib import Path
from pydantic import ValidationError
from tenacity import retry, stop_after_attempt, wait_fixed
from fastapi import HTTPException
from dotenv import load_dotenv
import google.generativeai as genai
from openai import OpenAI
from backend.models import CareerData

load_dotenv()

class LLMProvider(str, Enum):
    GOOGLE = "google"
    LOCAL = "local"
    AUTO = "auto"

def get_google_client():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY is missing")
    project_id = os.getenv("GCP_PROJECT_ID")
    if project_id:
        os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
    genai.configure(api_key=api_key)
    # Use gemini-2.5-flash since 2.0 is retired for new tokens in this environment
    return genai.GenerativeModel('gemini-2.5-flash', generation_config={"response_mime_type": "application/json"})

def get_local_client():
    # As per prompt, LM Studio runs at http://host.docker.internal:1234/v1
    # If not on docker, this can be handled by docker-compose extra_hosts
    base_url = "http://host.docker.internal:1234/v1"
    # Fallback to localhost if host.docker.internal fails? That will be local network configuration.
    return OpenAI(base_url=base_url, api_key="not-needed")

def read_master_data() -> str:
    master_md_path = Path(__file__).parent.parent / "MasterDataMDfileVER-4.md"
    try:
        if master_md_path.exists():
            return master_md_path.read_text(encoding="utf-8")
        else:
            return "No Master Data provided."
    except Exception as e:
        return f"Error reading Master Data: {str(e)}"

def format_system_prompt() -> str:
    master_facts = read_master_data()
    model_schema = CareerData.model_json_schema()
    
    return f"""You are CareerLens AI. Your task is to generate customized HTML placeholder values based on the inputs provided.
You MUST output a raw JSON object string ONLY. Do not include markdown blocks (e.g. ```json). Your response must strictly validate against the following JSON schema:
{json.dumps(model_schema, indent=2)}

Use the following candidate facts as reference when generating responses:
{master_facts}
"""

def generate_with_google(system_prompt: str, user_prompt: str) -> str:
    model = get_google_client()
    full_prompt = f"{system_prompt}\n\n{user_prompt}"
    response = model.generate_content(full_prompt)
    return response.text

def generate_with_local(system_prompt: str, user_prompt: str) -> str:
    client = get_local_client()
    response = client.chat.completions.create(
        model="local-model",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7
    )
    return response.choices[0].message.content

def try_generate_json(provider: LLMProvider, system_prompt: str, user_prompt: str) -> str:
    if provider == LLMProvider.AUTO:
        try:
            return generate_with_google(system_prompt, user_prompt)
        except Exception as e:
            print(f"Google API failed: {e}. Falling back to Local API.")
            return generate_with_local(system_prompt, user_prompt)
    elif provider == LLMProvider.GOOGLE:
        return generate_with_google(system_prompt, user_prompt)
    elif provider == LLMProvider.LOCAL:
        return generate_with_local(system_prompt, user_prompt)
    else:
        raise ValueError(f"Unknown provider: {provider}")


class JSONRecoveryRetryError(Exception):
    pass

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
def run_generation_with_retry(job_description: str, master_resume: str, attempt_history: dict = None) -> CareerData:
    provider_str = os.getenv("LLM_PROVIDER", "auto").lower()
    try:
        provider = LLMProvider(provider_str)
    except ValueError:
        provider = LLMProvider.AUTO
    
    if attempt_history is None:
        attempt_history = {"attempt": 0}
        
    attempt_history["attempt"] += 1
    
    system_prompt = format_system_prompt()
    if attempt_history["attempt"] > 1:
        system_prompt = "Your last response was not valid JSON. Respond with ONLY the raw JSON object, no markdown. " + system_prompt
        
    user_prompt = f"Job Description:\n{job_description}\n\nMaster Profile:\n{master_resume}"
    
    try:
        raw_output = try_generate_json(provider, system_prompt, user_prompt)
        # Attempt to parse
        # Very lightweight cleanup just in case LLM added markdown despite instructions
        if raw_output.startswith("```json"):
            raw_output = raw_output[7:]
        if raw_output.startswith("```"):
            raw_output = raw_output[3:]
        if raw_output.endswith("```"):
            raw_output = raw_output[:-3]
            
        parsed_json = json.loads(raw_output.strip())
        validated_data = CareerData(**parsed_json)
        return validated_data
        
    except (json.JSONDecodeError, ValidationError) as e:
        print(f"Validation or Parse error on attempt {attempt_history['attempt']}: {e}")
        raise JSONRecoveryRetryError(f"Failed to generate valid JSON: {str(e)}")
    except Exception as e:
        # Re-raise network/API errors entirely unless you want retry those? 
        # The prompt specifically mentions: "On retry, prepend system message: 'Your last response was not valid JSON'."
        # This implies retries are driven by validation failures. But we'll retry on all to be safe.
        print(f"API/Network error on attempt {attempt_history['attempt']}: {e}")
        raise

def generate_career_data(job_description: str, master_resume: str) -> CareerData:
    try:
        return run_generation_with_retry(job_description, master_resume, {"attempt": 0})
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"LLM Generation Failed after 3 attempts. Error: {str(e)}")
