import os
from google import genai
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

try:
    models = client.models.list()
    available = []
    for m in models:
        if "generateContent" in m.supported_actions:
            available.append(m.name)
            
    print(f"Probando {len(available)} modelos...")
    
    for model_name in available:
        try:
            # We don't use the 'models/' prefix for generate_content in the SDK usually, but let's extract the short name
            short_name = model_name.replace("models/", "")
            response = client.models.generate_content(
                model=short_name,
                contents="Di 'hola'"
            )
            print(f"[OK] {short_name} FUNCIONA!")
        except Exception as e:
            print(f"[FAIL] {short_name} FALLO: {e}")
            
except Exception as e:
    print(f"Error general: {e}")
