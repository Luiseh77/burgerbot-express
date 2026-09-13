import os
from google import genai
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

try:
    print("Available Models:")
    for m in client.models.list():
        if "generateContent" in m.supported_actions:
            print(f"- {m.name}")
except Exception as e:
    print("Error:", e)
