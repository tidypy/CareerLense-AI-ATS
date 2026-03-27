import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from openai import OpenAI
from typing import Optional

# Load .env from the root
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

def test_google_key(api_key: Optional[str]):
    print(f"\n--- Testing Google Gemini Key ---")
    if not api_key:
        print("Error: No Google API key provided.")
        return False
    
    try:
        genai.configure(api_key=api_key)
        # Using a small, fast model for testing
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content("Say 'Key is working!'")
        print(f"Response: {response.text.strip()}")
        print("RESULT: SUCCESS ✅")
        return True
    except google_exceptions.InvalidArgument:
        print("RESULT: FAILED ❌ (Invalid API Key)")
    except google_exceptions.ResourceExhausted:
        print("RESULT: FAILED ❌ (Quota Exhausted/No Credits)")
    except google_exceptions.PermissionDenied:
        print("RESULT: FAILED ❌ (Permission Denied - Check API enablement)")
    except Exception as e:
        print(f"RESULT: FAILED ❌ (Unexpected Error: {e})")
    return False

def test_local_endpoint(url: str):
    print(f"\n--- Testing Local LLM (LM Studio/Ollama) ---")
    if not url:
        print("Error: No URL provided.")
        return False
    
    # Simple check for common local LLM patterns
    base_url = url
    api_key = "not-needed"
    if "|" in url:
        parts = url.split("|")
        base_url = parts[0]
        if len(parts) > 1: api_key = parts[1]
        
    if not base_url.endswith("/v1"):
        base_url = base_url.rstrip("/") + "/v1"

    try:
        client = OpenAI(base_url=base_url, api_key=api_key)
        # Usually local LLMs have a model named 'local-model' or we just pick the first one
        models = client.models.list()
        model_id = models.data[0].id if models.data else "local-model"
        
        response = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": "Say 'Local LLM is working!'"}],
            max_tokens=10
        )
        print(f"Response: {response.choices[0].message.content.strip()}")
        print(f"RESULT: SUCCESS ✅ (Model: {model_id})")
        return True
    except Exception as e:
        print(f"RESULT: FAILED ❌ (Could not connect to {base_url}: {e})")
        return False

if __name__ == "__main__":
    print("CareerLens AI ATS - API Key Verification Tool")
    print("============================================")
    
    # 1. Check Google Key from .env or override
    google_key = os.getenv("GOOGLE_API_KEY")
    test_google_key(google_key)
    
    # 2. Check Local Endpoint
    local_url = os.getenv("LOCAL_LLM_URL", "http://localhost:1234/v1")
    test_local_endpoint(local_url)
    
    print("\nTip: If Google failed but you have an RTX card, ensure LOCAL_LLM_URL is set.")
