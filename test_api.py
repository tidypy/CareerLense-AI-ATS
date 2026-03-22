import os
import google.generativeai as genai

KEY = os.environ.get("GOOGLE_API_KEY")
PROJECT_ID = os.environ.get("GCP_PROJECT_ID")

if PROJECT_ID:
    # Adding to environment just in case google.auth requires it
    os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT_ID

genai.configure(
    api_key=KEY,
    client_options={"default_metadata": (("x-goog-user-project", PROJECT_ID),)} if PROJECT_ID else None
)
model = genai.GenerativeModel('gemini-2.5-flash', generation_config={"response_mime_type": "application/json"})
print(model.generate_content('You MUST output a valid JSON string. {"test": "success"}').text)
