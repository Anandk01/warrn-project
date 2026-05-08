import requests

import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get('GEMINI_API_KEY')

def list_models():
    url = f'https://generativelanguage.googleapis.com/v1/models?key={API_KEY}'
    
    try:
        response = requests.get(url)
        print(f"Status: {response.status_code}")
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            if 'models' in result:
                print("\nAvailable models:")
                print("\nAvailable models:")
                for model in result['models']:
                    print(f"- {model['name']}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    list_models()