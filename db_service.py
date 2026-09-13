import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# Variables de entorno de Supabase
url: str = os.environ.get("SUPABASE_URL", "")
key: str = os.environ.get("SUPABASE_KEY", "")

# Inicializamos el cliente (si no hay keys, no explotará inmediatamente, pero fallará al usarlo)
try:
    supabase: Client = create_client(url, key)
except Exception as e:
    supabase = None
    print(f"Advertencia: No se pudo conectar a Supabase. Faltan las llaves en el .env: {e}")

def guardar_pedido_nuevo(datos_pedido: dict) -> dict:
    """
    Guarda un nuevo pedido en la base de datos con estado PENDIENTE.
    Devuelve los datos insertados (incluyendo el ID generado).
    """
    if not supabase: return None
    
    # Limpiar formato de números por si Gemini envía strings con $ o comas
    try:
        gran_total = float(str(datos_pedido.get("gran_total", 0)).replace("$", "").replace(",", "."))
    except ValueError:
        gran_total = 0.0

    # Preparamos el objeto para insertar adaptando los nuevos campos
    nuevo_registro = {
        "cliente_nombre": datos_pedido.get("cliente_nombre", "Cliente"),
        "direccion": f"Zona: {datos_pedido.get('zona_delivery', 'N/A')}",
        "ubicacion_maps": None,
        "metodo_pago": datos_pedido.get("metodo_pago", "No especificado"),
        "items": datos_pedido.get("items", []),  # Supabase maneja JSON/JSONB nativamente
        "total": gran_total,
        "estado": "ESPERANDO_PAGO",
        "repartidor_id": None
    }
    
    try:
        response = supabase.table("pedidos").insert(nuevo_registro).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        print(f"Error al guardar pedido: {e}")
        return None

def asignar_pedido_a_repartidor(pedido_id: int, repartidor_telefono: str) -> bool:
    """
    Intenta asignar un pedido a un repartidor SOLO si sigue pendiente.
    Esto evita que dos repartidores tomen el mismo pedido a la vez.
    """
    if not supabase: return False
    
    # Verificamos si sigue pendiente
    response = supabase.table("pedidos").select("estado").eq("id", pedido_id).execute()
    if not response.data or response.data[0]["estado"] != "PENDIENTE":
        return False # Ya fue tomado o no existe
        
    # Lo actualizamos
    update_response = supabase.table("pedidos").update({
        "estado": "ASIGNADO",
        "repartidor_id": repartidor_telefono
    }).eq("id", pedido_id).execute()
    
    return True if update_response.data else False

def marcar_pedido_en_camino(pedido_id: int, repartidor_telefono: str) -> bool:
    """
    El repartidor confirma que ya recogió la comida.
    """
    if not supabase: return False
    
    response = supabase.table("pedidos").update({
        "estado": "EN_CAMINO"
    }).eq("id", pedido_id).eq("repartidor_id", repartidor_telefono).execute()
    
    return True if response.data else False

def registrar_checkin(telefono: str) -> bool:
    """
    Registra el primer mensaje del día de un repartidor o admin.
    Captura específicamente la violación de llave única (código 23505) si ya existe.
    """
    if not supabase: return False
    
    import datetime
    import postgrest
    
    # Ajuste de zona horaria explícito para Venezuela (UTC-4)
    # Evita desfases si el servidor corre en UTC (ej. Render)
    tz_venezuela = datetime.timezone(datetime.timedelta(hours=-4))
    ahora = datetime.datetime.now(tz_venezuela)
    
    hoy = ahora.date().isoformat()
    hora_str = ahora.strftime("%H:%M:%S")
    
    nuevo_registro = {
        "repartidor_id": telefono,
        "fecha": hoy,
        "hora_primer_mensaje": hora_str
    }
    
    try:
        response = supabase.table("checkins_diarios").insert(nuevo_registro).execute()
        return True
    except postgrest.exceptions.APIError as e:
        # 23505 = unique_violation en PostgreSQL
        if e.code == '23505' or 'duplicate key' in str(e).lower() or 'unique constraint' in str(e).lower():
            return False # Ya existía (esperado), fallamos silenciosamente
        print(f"❌ Error de API de Supabase al registrar checkin para {telefono}: {e}")
        return False
    except Exception as e:
        print(f"❌ Error inesperado al registrar checkin para {telefono}: {e}")
        return False

def obtener_checkins_hoy() -> dict:
    """
    Devuelve un diccionario con {telefono: hora_primer_mensaje} de los que hicieron check-in hoy.
    """
    if not supabase: return {}
    
    import datetime
    tz_venezuela = datetime.timezone(datetime.timedelta(hours=-4))
    hoy = datetime.datetime.now(tz_venezuela).date().isoformat()
    
    # Se eliminó el "except Exception" genérico y silencioso.
    # Si esto falla (por timeout o red), lanzará la excepción explícitamente para no 
    # enmascarar un fallo técnico haciéndolo pasar por "nadie ha hecho checkin".
    response = supabase.table("checkins_diarios").select("*").eq("fecha", hoy).execute()
    return {row["repartidor_id"]: row["hora_primer_mensaje"] for row in response.data}
