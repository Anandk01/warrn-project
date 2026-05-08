import os
import time
from google import genai
from google.genai import types

# Model to use across all calls (with fallback)
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_FALLBACK_MODEL = "gemini-2.0-flash-lite"

class GeminiService:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.client = None
        if self.api_key:
            try:
                # Initialize with explicit API key — avoid setting GOOGLE_API_KEY to prevent conflict
                self.client = genai.Client(api_key=self.api_key)
                print(f"Gemini Service: Initialized with model '{GEMINI_MODEL}'")
            except Exception as e:
                print(f"Gemini Service: Failed to initialize client: {e}")

    def classify_intent(self, query):
        """Classifies the user's query with error handling."""
        if not self.client:
            return "general"
        
        prompt = f"""Classify the user query for an animal rescue platform:
- status_query: Asking about a specific report ID or animal case update.
- emergency: Reporting an immediate life-threatening situation (hit by car, bleeding).
- rag: Asking about animal care, rescue steps, or platform usage info.
- general: General talk or unrelated.

Query: "{query}"
Respond with ONLY: status_query, emergency, rag, or general."""
        
        try:
            response = self.client.models.generate_content(
                model=GEMINI_MODEL, 
                contents=prompt
            )
            intent = response.text.strip().lower()
            print(f"Gemini Intent: '{intent}' for query: '{query[:50]}...'")
            return intent if intent in ["status_query", "emergency", "rag", "general"] else "general"
        except Exception as e:
            error_str = str(e)
            print(f"Gemini Intent Error ({GEMINI_MODEL}): {type(e).__name__}: {error_str}")
            # Retry with fallback model on quota/rate errors
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                try:
                    print(f"Retrying intent classification with fallback model: {GEMINI_FALLBACK_MODEL}")
                    response = self.client.models.generate_content(
                        model=GEMINI_FALLBACK_MODEL, 
                        contents=prompt
                    )
                    intent = response.text.strip().lower()
                    return intent if intent in ["status_query", "emergency", "rag", "general"] else "general"
                except Exception as e2:
                    print(f"Gemini Fallback Intent Error: {type(e2).__name__}: {e2}")
            return "general"

    def generate_response(self, query, context=None, is_status=False):
        """Generates a grounded response with automatic model fallback."""
        if not self.client:
            return "WARRN Assistant is currently offline. Please try again later."

        if is_status:
            system_instruction = "You are the WARRN Smart Assistant. Convert database data into an empathetic update. If ID not found, ask for correct ID."
        elif context:
            system_instruction = "You are the WARRN Smart Assistant. Answer using the provided context. Be factual."
        else:
            system_instruction = "You are the WARRN Smart Assistant. Expert in animal rescue. Be helpful and professional."

        contents = f"Query: {query}\n\nContext: {context if context else 'N/A'}"
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.7,
            max_output_tokens=500
        )

        # Try primary model first
        for model in [GEMINI_MODEL, GEMINI_FALLBACK_MODEL]:
            try:
                print(f"Gemini generating with model: {model}")
                response = self.client.models.generate_content(
                    model=model,
                    config=config,
                    contents=contents
                )
                return response.text.strip()
            except Exception as e:
                error_str = str(e)
                print(f"Gemini Error ({model}): {type(e).__name__}: {error_str}")
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    continue  # Try the next model
                elif "404" in error_str or "not found" in error_str.lower():
                    continue  # Model not available, try next
                return f"I encountered an error: {type(e).__name__}. Please try again."

        return "Our AI is currently busy. Please try again in a minute."

# Singleton instance
gemini_service = GeminiService()
