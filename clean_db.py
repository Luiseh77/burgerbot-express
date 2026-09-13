import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
url = os.environ.get("SUPABASE_URL", "")
key = os.environ.get("SUPABASE_KEY", "")
supabase = create_client(url, key)

# Mover todos los ESPERANDO_PAGO a RECHAZADO para destrabar el bot
response = supabase.table("pedidos").update({"estado": "RECHAZADO"}).eq("estado", "ESPERANDO_PAGO").execute()
print("Pedidos actualizados:", len(response.data))
