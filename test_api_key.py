"""Quick test to verify Gemini API key works."""
import os
from dotenv import load_dotenv
load_dotenv()

from google import genai

api_key = os.getenv("GEMINI_API_KEY")
print(f"API Key: {api_key[:10]}...{api_key[-4:]}")

client = genai.Client(api_key=api_key)

# Try all models to see which works
for model in ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash"]:
    try:
        response = client.models.generate_content(model=model, contents="Say hello in 5 words")
        print(f"OK {model}: {response.text.strip()}")
    except Exception as e:
        print(f"FAIL {model}: {str(e)[:200]}")
