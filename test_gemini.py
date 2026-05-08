import os
from google import genai
from dotenv import load_dotenv

# 1. Load your .env file
load_dotenv() 

def get_gemini_client():
    api_key = os.getenv("GEMINI_API_KEY")
    
    # 2. FORCE the environment variables (solves "API Key not found" bugs)
    os.environ["GOOGLE_API_KEY"] = api_key
    os.environ["GEMINI_API_KEY"] = api_key
    
    # 3. Initialize without arguments (most stable way)
    return genai.Client()

def ask_gemini(prompt):
    client = get_gemini_client()
    
    # 4. Use the specific model ID available to you
    model_id = "gemini-3-flash-preview" 
    
    try:
        response = client.models.generate_content(
            model=model_id,
            contents=prompt  # Always use 'contents='
        )
        return response.text
    except Exception as e:
        return f"Error: {e}"

# Usage
if __name__ == "__main__":
    print(ask_gemini("Hello, how are you?"))
