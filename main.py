import os
import sys
import json
import asyncio
from fastapi import FastAPI, Request, HTTPException, Query, BackgroundTasks
from fastapi.responses import PlainTextResponse
import uvicorn
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta

# Forzar salida en utf-8 para no tener problemas con emojis en consola de Windows
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass


from ai_service import obtener_respuesta_ia
from db_service import guardar_pedido_nuevo, supabase, marcar_pedido_en_camino, registrar_checkin, obtener_checkins_hoy
from whatsapp_service import enviar_mensaje_texto, enviar_botones_aprobacion, enviar_broadcast_deliverys, enviar_boton_recibido

load_dotenv()

app = FastAPI(title="BurgerBot Express Webhook")

# ============================================================
# DEDUPLICACIÓN DE WEBHOOKS (Bug 2 — mensajes duplicados de Meta)
# ============================================================
mensajes_procesados_recientes: dict = {}  # {wamid: unix_timestamp}

def ya_fue_procesado(wamid: str) -> bool:
    """Retorna True si este wamid ya fue procesado en los últimos 60s."""
    ahora = datetime.now(timezone.utc).timestamp()
    # Limpieza automática de entradas viejas
    for w in list(mensajes_procesados_recientes.keys()):
        if ahora - mensajes_procesados_recientes[w] > 60:
            del mensajes_procesados_recientes[w]
    if wamid in mensajes_procesados_recientes:
        return True
    mensajes_procesados_recientes[wamid] = ahora
    return False

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "")
ADMIN_PHONE = os.getenv("ADMIN_PHONE", "")

RESPUESTAS_POR_ESTADO = {
    "PAGO_POR_VALIDAR": "Hemos recibido tu pago y lo estamos verificando. En breve te confirmaremos. ⏳",
    "PENDIENTE": "Tu pedido ya está confirmado y estamos coordinando un repartidor. Te avisaremos apenas esté en camino. 🛵",
    "ASIGNADO": "¡Tu pedido ya fue asignado a un repartidor y va en camino! 🚀",
    "EN_CAMINO": "¡Tu pedido va en camino! Te avisaremos cuando el repartidor esté cerca. 📍"
}

# Archivos locales para persistencia
REPARTIDORES_FILE = "repartidores.json"
ADMINISTRADORES_FILE = "administradores.json"
TASA_FILE = "tasa.json"

def cargar_administradores():
    if not supabase: return {"584140881670": {"nombre": "Luis", "rol": "superadmin", "activo": True}}
    try:
        res = supabase.table("administradores").select("*").execute()
        if res.data:
            return {r["telefono"]: {"nombre": r["nombre"], "rol": r["rol"], "activo": r["activo"]} 
                    for r in res.data if r.get("activo", True)}
        # Fallback en caso de que la tabla esté vacía
        return {"584140881670": {"nombre": "Luis", "rol": "superadmin", "activo": True}}
    except Exception as e:
        print(f"Error cargando administradores: {e}")
        return {"584140881670": {"nombre": "Luis", "rol": "superadmin", "activo": True}}

def guardar_administradores(admins_dict):
    if not supabase: return
    try:
        lista_upsert = [{"telefono": k, "nombre": v["nombre"], "rol": v.get("rol", "admin"), "activo": v.get("activo", True)} for k, v in admins_dict.items()]
        if lista_upsert:
            supabase.table("administradores").upsert(lista_upsert).execute()
    except Exception as e:
        print(f"Error guardando administradores en Supabase: {e}")

def es_administrador(telefono: str) -> bool:
    if not ADMIN_PHONE:
        return False
    # El Súper Admin siempre es admin
    if telefono == ADMIN_PHONE:
        return True
    # Revisamos secundarios
    admins = cargar_administradores()
    return telefono in admins

def notificar_a_todos_admins_con_botones(pedido_id: str):
    admins = cargar_administradores()
    destinatarios = set([ADMIN_PHONE]) | set(admins.keys()) if ADMIN_PHONE else set(admins.keys())
    for tel in destinatarios:
        enviar_botones_aprobacion(tel, pedido_id)

def notificar_a_todos_admins_texto(mensaje: str):
    admins = cargar_administradores()
    destinatarios = set([ADMIN_PHONE]) | set(admins.keys()) if ADMIN_PHONE else set(admins.keys())
    for tel in destinatarios:
        enviar_mensaje_texto(tel, mensaje)


def cargar_repartidores():
    if not supabase: return {}
    try:
        res = supabase.table("repartidores").select("*").execute()
        if res.data:
            # Filtramos para devolver solo los que están activos y en el formato esperado
            return {r["telefono"]: {"nombre": r["nombre"], "disponible": r["disponible"], "activo": r["activo"]} 
                    for r in res.data if r.get("activo", True)}
        return {}
    except Exception as e:
        print(f"Error cargando repartidores desde Supabase: {e}")
        return {}

def guardar_repartidores(repartidores_dict):
    if not supabase: return
    try:
        lista_upsert = [{"telefono": k, "nombre": v["nombre"], "disponible": v.get("disponible", True), "activo": v.get("activo", True)} for k, v in repartidores_dict.items()]
        if lista_upsert:
            supabase.table("repartidores").upsert(lista_upsert).execute()
    except Exception as e:
        print(f"Error guardando repartidores en Supabase: {e}")

def cargar_metodos_pago():
    if os.path.exists("metodos_pago.json"):
        try:
            with open("metodos_pago.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    # Fallback por defecto si no existe el archivo
    return {
        "pago_movil": {
            "nombre": "Pago Móvil",
            "detalles": f"Banco: {os.getenv('PAGO_MOVIL_BANCO', '0102')}, CI: {os.getenv('PAGO_MOVIL_CI', 'V12345678')}, Tlf: {os.getenv('PAGO_MOVIL_TLF', '04140000000')}",
            "activo": True,
            "banco": os.getenv("PAGO_MOVIL_BANCO", "0102"),
            "telefono": os.getenv("PAGO_MOVIL_TLF", "04140000000"),
            "cedula": os.getenv("PAGO_MOVIL_CI", "V12345678")
        },
        "zelle": {
            "nombre": "Zelle",
            "detalles": f"Correo: {os.getenv('ZELLE_EMAIL', 'pagos@burgerbot.fake')}, A nombre de: BurgerBot Express",
            "activo": True
        }
    }

def guardar_metodos_pago(pagos_dict):
    with open("metodos_pago.json", "w", encoding="utf-8") as f:
        json.dump(pagos_dict, f, ensure_ascii=False, indent=4)

def obtener_tasa_bcv():
    # 1. Revisar si hay una tasa manual de emergencia fijada
    if os.path.exists(TASA_FILE):
        try:
            with open(TASA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "tasa_manual" in data:
                    return data["tasa_manual"]
        except:
            pass
            
    # 2. Si no hay tasa manual, conectarse al BCV vía DolarAPI
    try:
        import requests
        resp = requests.get("https://ve.dolarapi.com/v1/dolares/oficial", timeout=5)
        if resp.status_code == 200:
            return float(resp.json()["promedio"])
    except Exception as e:
        print(f"Error consultando BCV: {e}")
        
    return 40.0 # Tasa fallback de seguridad en caso extremo


# Memoria de sesión temporal en RAM
SESSION_MEMORY = {}

@app.get("/")
async def root():
    return {"message": "El servidor de Supremo Delivery está activo y escuchando."}

@app.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
):
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        print("✅ ¡Webhook verificado por Meta!")
        return PlainTextResponse(content=hub_challenge)
    raise HTTPException(status_code=403, detail="Error de autenticación")

@app.post("/webhook")
async def webhook_whatsapp(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()
    
    if body.get("object"):
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                
                if "messages" in value:
                    for msg in value["messages"]:
                        # Bug 2: Ignorar webhooks duplicados que Meta reenvía
                        wamid = msg.get("id", "")
                        if wamid and ya_fue_procesado(wamid):
                            print(f"⚠️ Webhook duplicado ignorado: {wamid}")
                            continue

                        telefono_cliente = msg["from"]
                        
                        # --- CHECK-IN DIARIO PARA STAFF ---
                        if es_administrador(telefono_cliente) or telefono_cliente in cargar_repartidores():
                            background_tasks.add_task(registrar_checkin, telefono_cliente)
                            
                        if msg["type"] == "text":
                            texto = msg["text"]["body"]
                            print(f"💬 Mensaje de {telefono_cliente}: {texto}")
                            background_tasks.add_task(handle_texto, telefono_cliente, texto)
                            
                        elif msg["type"] == "image":
                            print(f"📸 Imagen recibida de {telefono_cliente}")
                            background_tasks.add_task(handle_imagen, telefono_cliente)
                            
                        elif msg["type"] == "interactive":
                            try:
                                boton_id = msg["interactive"]["button_reply"]["id"]
                                print(f"👆 Botón presionado por {telefono_cliente}: {boton_id}")
                                background_tasks.add_task(handle_boton, telefono_cliente, boton_id)
                            except KeyError:
                                pass # Puede ser un list_reply
                        
                        elif msg["type"] == "location":
                            print(f"📍 Ubicación recibida de {telefono_cliente}")
                            lat = msg["location"]["latitude"]
                            lng = msg["location"]["longitude"]
                            background_tasks.add_task(handle_ubicacion, telefono_cliente, lat, lng)

    return {"status": "ok"}

async def procesar_datos_entrega(telefono: str, texto_direccion: str = None, link_maps: str = None):
    if not supabase: return False
    
    estados_entrega = ["ESPERANDO_DIRECCION", "ESPERANDO_UBICACION"]
    response = supabase.table("pedidos").select("*").in_("estado", estados_entrega).execute()
    
    pedido = None
    if response.data:
        for p in reversed(response.data):
            if telefono in str(p.get("cliente_nombre", "")):
                pedido = p
                break
                
    if not pedido:
        return False
        
    pedido_id = pedido["id"]
    
    dir_actual = pedido.get("direccion", "")
    maps_actual = pedido.get("ubicacion_maps")
    
    cambios = {}
    
    if texto_direccion:
        if "|" not in dir_actual:
            cambios["direccion"] = f"{dir_actual} | Dirección: {texto_direccion}"
        else:
            cambios["direccion"] = f"{dir_actual.split('|')[0].strip()} | Dirección: {texto_direccion}"
            
    if link_maps:
        cambios["ubicacion_maps"] = link_maps
        
    dir_evaluar = cambios.get("direccion", dir_actual)
    maps_evaluar = cambios.get("ubicacion_maps", maps_actual)
    
    tiene_direccion = "|" in dir_evaluar
    tiene_maps = maps_evaluar is not None and maps_evaluar.strip() != ""
    
    if tiene_direccion and tiene_maps:
        cambios["estado"] = "PENDIENTE"
        supabase.table("pedidos").update(cambios).eq("id", pedido_id).execute()
        
        # Broadcast a repartidores
        zona = dir_evaluar.split("|")[0].replace("Zona: ", "").strip() if "|" in dir_evaluar else "N/A"
        reps_dict = cargar_repartidores()
        telefonos_repartidores = [k for k, v in reps_dict.items() if isinstance(v, dict) and v.get("disponible", True)]
        
        if telefonos_repartidores:
            enviar_mensaje_texto(telefono, "🚀 ¡Excelente! Hemos recibido todos tus datos de entrega. Ya estamos preparando tu pedido y ubicando a un repartidor. Te avisaremos apenas vaya en camino. 🛵")
            enviar_broadcast_deliverys(telefonos_repartidores, str(pedido_id), zona, pedido["total"])
        else:
            notificar_a_todos_admins_texto(
                f"⚠️ Pedido #{pedido_id} confirmado pero NO hay repartidores disponibles ahora mismo. "
                f"Se notificará automáticamente al primero que marque DISPONIBLE."
            )
            enviar_mensaje_texto(
                telefono,
                "🚀 ¡Tu pedido está confirmado! Estamos coordinando un repartidor y te avisaremos apenas esté en camino. Gracias por tu paciencia 🙏"
            )
        
    elif tiene_direccion:
        cambios["estado"] = "ESPERANDO_UBICACION"
        supabase.table("pedidos").update(cambios).eq("id", pedido_id).execute()
        enviar_mensaje_texto(telefono, "📍 ¡Dirección recibida! Ahora, por favor envíanos tu **ubicación GPS**. Puedes hacerlo usando el botón de adjuntar ubicación en WhatsApp (Ubicación -> Enviar mi ubicación actual) o copiando y pegando el enlace de Google Maps.")
        
    elif tiene_maps:
        cambios["estado"] = "ESPERANDO_DIRECCION"
        supabase.table("pedidos").update(cambios).eq("id", pedido_id).execute()
        enviar_mensaje_texto(telefono, "📍 ¡Ubicación GPS recibida! Ahora, por favor envíanos tu **dirección exacta por escrito** (calle, número de casa, puntos de referencia) para completar tus datos.")
        
    return True

async def handle_ubicacion(telefono: str, lat: float, lng: float):
    # Verificamos si está esperando pago (ignorar ubicaciones en esta fase)
    if supabase:
        response = supabase.table("pedidos").select("*").eq("estado", "ESPERANDO_PAGO").like("cliente_nombre", f"%({telefono})%").execute()
        if response.data:
            enviar_mensaje_texto(telefono, "Por favor, envíame la foto o captura de pantalla de tu pago para poder procesar tu pedido.")
            return

        # Si está en fase de entrega, procesamos
        maps_link = f"https://maps.google.com/?q={lat},{lng}"
        procesado = await procesar_datos_entrega(telefono, link_maps=maps_link)
        if procesado:
            return

    if telefono not in SESSION_MEMORY:
        SESSION_MEMORY[telefono] = []
        
    # Generamos el link de Google Maps
    maps_link = f"https://maps.google.com/?q={lat},{lng}"
    
    # Lo agregamos al historial como si el usuario lo hubiera escrito
    SESSION_MEMORY[telefono].append({"role": "user", "content": f"Mi ubicación GPS enviada por WhatsApp es: {maps_link}"})
    
    # Procesamos la respuesta con la IA
    respuesta_ia = obtener_respuesta_ia(SESSION_MEMORY[telefono])
    
    if respuesta_ia["tipo"] == "texto":
        SESSION_MEMORY[telefono].append({"role": "assistant", "content": respuesta_ia["contenido"]})
        enviar_mensaje_texto(telefono, respuesta_ia["contenido"])
        
    elif respuesta_ia["tipo"] == "pedido_completado":
        datos_pedido = respuesta_ia["contenido"]
        resultado = guardar_pedido_nuevo(datos_pedido)
        if resultado:
            print(f"💾 Pedido {resultado['id']} guardado. Esperando pago.")
            
        texto_cobro = (
            f"¡Excelente {datos_pedido.get('cliente_nombre', '')}!\n\n"
            f"Tu pedido está confirmado. El Gran Total a pagar (incluyendo delivery) es: *${datos_pedido.get('gran_total', '')}*.\n\n"
            "Por favor, envíame por aquí la *captura de pantalla* del comprobante."
        )
        enviar_mensaje_texto(telefono, texto_cobro)

def generar_y_enviar_cobro(resultado: dict, telefono: str, nombre_original: str = None):
    if not nombre_original:
        # Extraer del nombre guardado "Nombre (telefono)"
        nombre_guardado = resultado.get('cliente_nombre', 'Cliente')
        nombre_original = nombre_guardado.split(' (')[0] if ' (' in nombre_guardado else nombre_guardado
        
    metodo_cliente = resultado.get('metodo_pago', '')
    
    tasa_actual = obtener_tasa_bcv()
    total_usd = float(resultado.get('total', 0))
    total_bs = round(total_usd * tasa_actual, 2)
    metodos = cargar_metodos_pago()
    
    if metodo_cliente == "Pago Móvil":
        detalles_pago = metodos.get("pago_movil", {}).get("detalles", "Datos de pago móvil no configurados")
    elif metodo_cliente == "Zelle":
        detalles_pago = metodos.get("zelle", {}).get("detalles", "Datos de Zelle no configurados")
    else: # Efectivo
        detalles_pago = "Pago en efectivo al momento de la entrega."
                
    texto_cobro = (
        f"¡Excelente {nombre_original}!\n\n"
        f"Tu pedido está confirmado. El Gran Total a pagar es: *${total_usd}*\n"
        f"*(Equivalente a {total_bs} Bs según tasa BCV de {tasa_actual})*\n\n"
        "Por favor, realiza tu pago y envíame por aquí la *captura de pantalla* del comprobante.\n\n"
        f"Instrucciones de Pago:\n{detalles_pago}"
    )
    enviar_mensaje_texto(telefono, texto_cobro)
    
    # Enviar formato pegable de Pago Móvil en mensaje separado
    if metodo_cliente == "Pago Móvil":
        pm = metodos.get("pago_movil", {})
        if pm:
            banco = pm.get("banco", "")
            tlf = pm.get("telefono", "")
            ced = pm.get("cedula", "")
            monto_formateado = f"{total_bs:.2f}".replace(".", ",")
            enviar_mensaje_texto(telefono, f"Banco: {banco}\nTeléfono: {tlf}\nCédula: {ced}\nMonto: {monto_formateado} Bs")

async def handle_texto(telefono: str, texto: str):
    texto_upper = texto.strip().upper()
    es_admin = es_administrador(telefono)
    es_repartidor = telefono in cargar_repartidores()

    # --- COMANDOS DE ADMINISTRADOR ---
    if es_admin:
        # --- COMANDOS EXCLUSIVOS DE SÚPER ADMINISTRADOR ---
        if telefono == ADMIN_PHONE:
            if texto_upper.startswith("AGREGAR ADMINISTRADOR"):
                partes = texto.split(maxsplit=3)
                if len(partes) >= 4:
                    num_nuevo = partes[2]
                    nom_nuevo = partes[3]
                    admins = cargar_administradores()
                    admins[num_nuevo] = {"nombre": nom_nuevo, "rol": "admin", "activo": True}
                    guardar_administradores(admins)
                    enviar_mensaje_texto(telefono, f"✅ Administrador secundario {nom_nuevo} agregado con el número {num_nuevo}.")
                else:
                    enviar_mensaje_texto(telefono, "❌ Formato incorrecto. Usa: AGREGAR ADMINISTRADOR numero_telefono nombre")
                return
                
            elif texto_upper.startswith("ELIMINAR ADMINISTRADOR"):
                # Formato esperado: ELIMINAR ADMINISTRADOR 584120000000
                partes = texto.split()
                if len(partes) >= 3:
                    num_borrar = partes[2]
                    admins = cargar_administradores()
                    if num_borrar in admins:
                        admins[num_borrar]["activo"] = False
                        nom_borrado = admins[num_borrar]["nombre"]
                        guardar_administradores(admins)
                        enviar_mensaje_texto(telefono, f"🗑️ Administrador secundario {nom_borrado} eliminado.")
                    else:
                        enviar_mensaje_texto(telefono, "❌ Ese número no está registrado como administrador secundario.")
                else:
                    enviar_mensaje_texto(telefono, "❌ Formato incorrecto. Usa: ELIMINAR ADMINISTRADOR numero_telefono")
                return
                
            elif texto_upper == "VER ADMINISTRADORES":
                admins = cargar_administradores()
                lista = "📋 *ADMINISTRADORES SECUNDARIOS:*\n"
                for num, datos in admins.items():
                    nom = datos.get("nombre", "Admin") if isinstance(datos, dict) else datos
                    lista += f"• {nom} ({num})\n"
                enviar_mensaje_texto(telefono, lista)
                return

        # --- COMANDOS ADMINISTRATIVOS COMUNES ---
        if texto_upper in ["DISPONIBLES", "QUIEN ESTA ACTIVO", "QUIÉN ESTÁ ACTIVO"]:
            reps = cargar_repartidores()
            admins = cargar_administradores()
            # Unir todo el staff (excepto super admin temporalmente o incluirlo si se quiere)
            staff = reps.copy()
            staff.update(admins)
            if ADMIN_PHONE:
                staff[ADMIN_PHONE] = "Súper Admin"
                
            checkins = obtener_checkins_hoy()
            
            lista = "📋 *STAFF ACTIVO HOY (Con ventana de 24h abierta):*\n\n"
            activos = 0
            for num, nom in staff.items():
                if num in checkins:
                    lista += f"✅ {nom} (Desde: {checkins[num]})\n"
                    activos += 1
            
            if activos < len(staff):
                lista += "\n💤 *Aún no han hecho Check-in hoy:*\n"
                for num, nom in staff.items():
                    if num not in checkins:
                        lista += f"❌ {nom}\n"
            
            enviar_mensaje_texto(telefono, lista)
            return

        elif texto_upper.startswith("AGREGAR REPARTIDOR"):
            partes = texto.split(maxsplit=3)
            if len(partes) >= 4:
                num_nuevo = partes[2]
                nombre_nuevo = partes[3]
                reps = cargar_repartidores()
                reps[num_nuevo] = {"nombre": nombre_nuevo, "disponible": True, "activo": True}
                guardar_repartidores(reps)
                enviar_mensaje_texto(telefono, f"✅ Repartidor {nombre_nuevo} agregado con el número {num_nuevo}.")
            else:
                enviar_mensaje_texto(telefono, "❌ Formato incorrecto. Usa: AGREGAR REPARTIDOR numero_telefono nombre")
            return
            
        elif texto_upper.startswith("ELIMINAR REPARTIDOR"):
            # Formato esperado: ELIMINAR REPARTIDOR 584120000000
            partes = texto.split()
            if len(partes) >= 3:
                num_borrar = partes[2]
                reps = cargar_repartidores()
                if num_borrar in reps:
                    # En vez de pop, lo marcamos como inactivo para que se guarde en DB con activo=False
                    reps[num_borrar]["activo"] = False
                    nombre_borrado = reps[num_borrar]["nombre"]
                    guardar_repartidores(reps)
                    enviar_mensaje_texto(telefono, f"🗑️ Repartidor {nombre_borrado} eliminado de la libreta.")
                else:
                    enviar_mensaje_texto(telefono, "❌ Ese número no está registrado.")
            else:
                enviar_mensaje_texto(telefono, "❌ Formato incorrecto. Usa: ELIMINAR REPARTIDOR numero_telefono")
            return
            
        elif texto_upper == "VER REPARTIDORES":
            reps = cargar_repartidores()
            lista = "📋 *TUS REPARTIDORES:*\n"
            for num, datos in reps.items():
                nom = datos.get("nombre", "Desconocido") if isinstance(datos, dict) else datos
                estado = "🟢 Disp." if isinstance(datos, dict) and datos.get("disponible") else "🔴 Ocup."
                lista += f"• {nom} ({num}) - {estado}\n"
            enviar_mensaje_texto(telefono, lista)
            return
 
        elif texto_upper.startswith("FIJAR TASA"):
            partes = texto.split()
            if len(partes) >= 3:
                try:
                    nueva_tasa = float(partes[2].replace(",", "."))
                    with open(TASA_FILE, "w", encoding="utf-8") as f:
                        json.dump({"tasa_manual": nueva_tasa}, f)
                    enviar_mensaje_texto(telefono, f"✅ Tasa manual fijada en {nueva_tasa} Bs. El bot ya no usará la tasa de internet.")
                except ValueError:
                    enviar_mensaje_texto(telefono, "❌ Formato incorrecto. Usa: FIJAR TASA 38.50")
            return
            
        elif texto_upper == "VER PAGOS":
            metodos = cargar_metodos_pago()
            lista = "📋 *MÉTODOS DE PAGO REGISTRADOS:*\n"
            for k, v in metodos.items():
                estado = "🟢 Activo" if v.get("activo", True) else "🔴 Inactivo"
                lista += f"• [{k}] {v['nombre']} - {estado}\n  Detalles: {v['detalles']}\n"
            enviar_mensaje_texto(telefono, lista)
            return
            
        elif texto_upper.startswith("AGREGAR PAGO"):
            partes = texto.split(" ", 2)
            if len(partes) >= 3:
                metodo_data = partes[2].split("|", 1)
                if len(metodo_data) == 2:
                    pago_id_full = metodo_data[0].strip()
                    if " " in pago_id_full:
                        pago_id, pago_nombre = pago_id_full.split(" ", 1)
                        pago_id = pago_id.lower()
                    else:
                        pago_id = pago_id_full.lower()
                        pago_nombre = pago_id_full
                    pago_detalles = metodo_data[1].strip()
                    
                    metodos = cargar_metodos_pago()
                    metodos[pago_id] = {"nombre": pago_nombre, "detalles": pago_detalles, "activo": True}
                    guardar_metodos_pago(metodos)
                    enviar_mensaje_texto(telefono, f"✅ Método de pago '{pago_nombre}' [{pago_id}] agregado.")
                else:
                    enviar_mensaje_texto(telefono, "❌ Formato incorrecto. Usa: AGREGAR PAGO id Nombre | Detalles")
            else:
                enviar_mensaje_texto(telefono, "❌ Formato incorrecto. Usa: AGREGAR PAGO id Nombre | Detalles")
            return

        elif texto_upper.startswith("ELIMINAR PAGO"):
            pago_id = texto.split()[-1].lower()
            metodos = cargar_metodos_pago()
            if pago_id in metodos:
                nombre = metodos.pop(pago_id)["nombre"]
                guardar_metodos_pago(metodos)
                enviar_mensaje_texto(telefono, f"🗑️ Método de pago '{nombre}' [{pago_id}] eliminado.")
            else:
                enviar_mensaje_texto(telefono, f"❌ El método de pago [{pago_id}] no existe.")
            return
 
        elif texto_upper.startswith("ACTIVAR PAGO"):
            pago_id = texto.split()[-1].lower()
            metodos = cargar_metodos_pago()
            if pago_id in metodos:
                metodos[pago_id]["activo"] = True
                guardar_metodos_pago(metodos)
                enviar_mensaje_texto(telefono, f"🟢 Método de pago '{metodos[pago_id]['nombre']}' [{pago_id}] activado.")
            else:
                enviar_mensaje_texto(telefono, f"❌ El método de pago [{pago_id}] no existe.")
            return
 
        elif texto_upper.startswith("DESACTIVAR PAGO"):
            pago_id = texto.split()[-1].lower()
            metodos = cargar_metodos_pago()
            if pago_id in metodos:
                metodos[pago_id]["activo"] = False
                guardar_metodos_pago(metodos)
                enviar_mensaje_texto(telefono, f"🔴 Método de pago '{metodos[pago_id]['nombre']}' [{pago_id}] desactivado.")
            else:
                enviar_mensaje_texto(telefono, f"❌ El método de pago [{pago_id}] no existe.")
            return
 
        elif texto_upper == "BORRAR TASA":
            if os.path.exists(TASA_FILE):
                os.remove(TASA_FILE)
            enviar_mensaje_texto(telefono, "✅ Tasa manual borrada. El bot vuelve a usar la tasa automática del BCV por internet.")
            return

    # --- COMANDOS DE REPARTIDOR ---
    if es_repartidor:
        if texto_upper == "DISPONIBLE":
            if supabase:
                resultado = supabase.table("repartidores").update({"disponible": True}).eq("telefono", telefono).execute()
                if resultado.data:
                    enviar_mensaje_texto(telefono, "✅ Quedaste marcado como DISPONIBLE. Te llegarán los próximos pedidos.")
                    
                    # Recuperación automática de pedidos huérfanos
                    # Bug 1: Solo pedidos de las últimas 3h y en orden correlativo
                    limite = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
                    pendientes = supabase.table("pedidos").select("*") \
                        .eq("estado", "PENDIENTE") \
                        .is_("repartidor_id", "null") \
                        .gte("created_at", limite) \
                        .order("created_at", desc=False) \
                        .execute()
                    if pendientes.data:
                        for p in pendientes.data:
                            zona = p.get("direccion", "").split("|")[0].replace("Zona: ", "").strip()
                            enviar_broadcast_deliverys([telefono], str(p["id"]), zona, p.get("total", 0))
                else:
                    enviar_mensaje_texto(telefono, "⚠️ Hubo un problema actualizando tu estado, intenta de nuevo.")
            else:
                enviar_mensaje_texto(telefono, "⚠️ Base de datos no conectada.")
            return

        elif texto_upper == "OCUPADO":
            if supabase:
                resultado = supabase.table("repartidores").update({"disponible": False}).eq("telefono", telefono).execute()
                if resultado.data:
                    enviar_mensaje_texto(telefono, "🔴 Quedaste marcado como OCUPADO. No recibirás nuevos pedidos hasta que escribas DISPONIBLE.")
                else:
                    enviar_mensaje_texto(telefono, "⚠️ Hubo un problema actualizando tu estado, intenta de nuevo.")
            else:
                enviar_mensaje_texto(telefono, "⚠️ Base de datos no conectada.")
            return

    # ============================================================
    # BARRERA DE CONTENCIÓN: Staff nunca debe llegar a Gemini
    # ============================================================
    if es_admin or es_repartidor:
        if es_admin:
            menu = (
                "🔧 *Comando no reconocido.*\n\n"
                "📋 *Comandos disponibles (Admin):*\n"
                "• AGREGAR ADMINISTRADOR <tel> <nombre>\n"
                "• ELIMINAR ADMINISTRADOR <tel>\n"
                "• AGREGAR REPARTIDOR <tel> <nombre>\n"
                "• ELIMINAR REPARTIDOR <tel>\n"
                "• VER ADMINISTRADORES\n"
                "• VER REPARTIDORES\n"
                "• FIJAR TASA <valor>\n"
                "• ELIMINAR PAGO <id>"
            )
        else:
            menu = (
                "🔧 *Comando no reconocido.*\n\n"
                "📋 *Comandos disponibles (Repartidor):*\n"
                "• DISPONIBLE\n"
                "• OCUPADO"
            )
        enviar_mensaje_texto(telefono, menu)
        return

    # --- A partir de aquí, el mensaje es estrictamente de un CLIENTE ---

    # 1. Verificar si el cliente tiene un pedido en ESPERANDO_PAGO
    if supabase:
        # 0.5 Verificar si está esperando MÉTODO DE PAGO
        resp_metodo = supabase.table("pedidos").select("*").eq("estado", "ESPERANDO_METODO_PAGO").eq("telefono", telefono).execute()
        if resp_metodo.data:
            pedido_actual = resp_metodo.data[0]
            texto_lower = texto.lower().strip()
            
            METODOS_VALIDOS = {"efectivo": "Efectivo", "zelle": "Zelle", "pago movil": "Pago Móvil", "pago móvil": "Pago Móvil", "movil": "Pago Móvil", "móvil": "Pago Móvil"}
            metodo_encontrado = next((v for k, v in METODOS_VALIDOS.items() if k in texto_lower), None)
            
            if metodo_encontrado:
                pedido_actual["metodo_pago"] = metodo_encontrado
                pedido_actual["estado"] = "ESPERANDO_PAGO"
                supabase.table("pedidos").update({"metodo_pago": metodo_encontrado, "estado": "ESPERANDO_PAGO"}).eq("id", pedido_actual["id"]).execute()
                print(f"🔄 Pedido {pedido_actual['id']} actualizado con método de pago: {metodo_encontrado}")
                generar_y_enviar_cobro(pedido_actual, telefono)
            else:
                enviar_mensaje_texto(telefono, "No logré identificar tu método de pago. Por favor escribe: Efectivo, Pago Móvil o Zelle.")
            return

        # 1. Verificar si el cliente tiene un pedido en ESPERANDO_PAGO
        response = supabase.table("pedidos").select("*").eq("estado", "ESPERANDO_PAGO").execute()
        tiene_pendiente = any(telefono in str(p.get("cliente_nombre", "")) for p in (response.data or []))
        if tiene_pendiente:
            texto_lower = texto.lower().strip()
            if any(w in texto_lower for w in ["zelle", "efectivo", "pago movil", "pago móvil", "movil", "móvil"]):
                enviar_mensaje_texto(telefono, "Veo que quieres cambiar tu método de pago. Si el error fue nuestro, avísale al administrador escribiendo AYUDA, o si prefieres, cancela este pedido y hagamos uno nuevo con el método correcto.")
            else:
                enviar_mensaje_texto(telefono, "⚠️ Tienes un pedido pendiente por pagar. Por favor, envíame la foto o captura de pantalla de tu pago para poder procesarlo. Si deseas cancelar ese pedido y empezar de nuevo, por favor contacta al administrador.")
            return

        # 1.5 Verificar si está en fase de recolección de dirección / ubicación
        estados_entrega = ["ESPERANDO_DIRECCION", "ESPERANDO_UBICACION"]
        resp_ent = supabase.table("pedidos").select("*").in_("estado", estados_entrega).execute()
        tiene_ent = any(telefono in str(p.get("cliente_nombre", "")) for p in (resp_ent.data or []))
        if tiene_ent:
            if "maps" in texto.lower() or "http" in texto.lower() or "google.com/maps" in texto.lower():
                await procesar_datos_entrega(telefono, link_maps=texto)
            else:
                await procesar_datos_entrega(telefono, texto_direccion=texto)
            return

        # 1.8 Verificar si tiene un pedido activo en curso (evitar que hable con Gemini)
        resp_pedido_activo = supabase.table("pedidos").select("*").in_("estado", list(RESPUESTAS_POR_ESTADO.keys())).execute()
        pedido_activo = next((p for p in (resp_pedido_activo.data or []) if telefono in str(p.get("cliente_nombre", ""))), None)
        if pedido_activo:
            enviar_mensaje_texto(telefono, RESPUESTAS_POR_ESTADO[pedido_activo["estado"]])
            return

    # 2. Si no está en un estado bloqueante, es un chat normal con la IA
    if telefono not in SESSION_MEMORY:
        SESSION_MEMORY[telefono] = []
        
    # Añadimos el mensaje del usuario al historial
    SESSION_MEMORY[telefono].append({"role": "user", "content": texto})
        
    # Le pasamos el historial a la IA
    respuesta_ia = obtener_respuesta_ia(SESSION_MEMORY[telefono])
    
    if respuesta_ia["tipo"] == "texto":
        SESSION_MEMORY[telefono].append({"role": "assistant", "content": respuesta_ia["contenido"]})
        # Red de seguridad: detectar si Gemini habló de cobro sin llamar a finalizar_pedido
        contenido_lower = respuesta_ia["contenido"].lower()
        if any(x in contenido_lower for x in ["gran total", "captura de pantalla", "pago móvil", "zelle", "transfiere"]):
            print(f"⚠️ ALERTA: Gemini mencionó términos de cobro sin llamar a finalizar_pedido para {telefono}")
        enviar_mensaje_texto(telefono, respuesta_ia["contenido"])
        
    elif respuesta_ia["tipo"] == "pedido_completado":
        datos_pedido = respuesta_ia["contenido"]

        metodo_cliente = datos_pedido.get('metodo_pago', '')
        

        # Inject phone number into name to track it without altering DB schema
        nombre_original = datos_pedido.get('cliente_nombre', 'Cliente')
        datos_pedido["cliente_nombre"] = f"{nombre_original} ({telefono})"
        
        # Guardar el teléfono real en la nueva columna de DB
        datos_pedido["telefono"] = telefono
        
        if not metodo_cliente:
            resultado = guardar_pedido_nuevo(datos_pedido, estado_inicial="ESPERANDO_METODO_PAGO")
            if resultado:
                print(f"💾 Pedido {resultado['id']} guardado sin método. Esperando método de pago.")
                enviar_mensaje_texto(telefono, f"¡Gracias {nombre_original}! Solo me falta un dato: ¿cómo vas a pagar? (Efectivo, Pago Móvil o Zelle)")
            return
            
        if metodo_cliente not in ["Efectivo", "Pago Móvil", "Zelle"]:
            print(f"⚠️ metodo_pago inesperado: {metodo_cliente}")
            enviar_mensaje_texto(telefono, "¿Me podrías confirmar tu método de pago? (Efectivo, Pago Móvil o Zelle)")
            return

        resultado = guardar_pedido_nuevo(datos_pedido, estado_inicial="ESPERANDO_PAGO")
        if resultado:
            print(f"💾 Pedido {resultado['id']} guardado. Esperando pago.")
            generar_y_enviar_cobro(resultado, telefono, nombre_original)
        else:
            print("❌ Error fatal: La base de datos no pudo guardar el pedido.")
            enviar_mensaje_texto(telefono, "❌ Lo siento, hubo un error técnico al registrar tu pedido. Por favor, intenta hacer el pedido nuevamente.")

async def handle_imagen(telefono: str):
    # Si manda imagen, buscamos si hay un pedido en ESPERANDO_PAGO de este teléfono
    if not supabase: return
    
    pedido_encontrado = None
    intentos = 3
    espera_segundos = 1.5

    for intento in range(intentos):
        response = supabase.table("pedidos").select("*").eq("estado", "ESPERANDO_PAGO").execute()
        if response.data:
            for p in response.data:
                # Busca en columna nueva 'telefono' primero, o hace fallback a cliente_nombre
                if p.get("telefono") == telefono or telefono in str(p.get("cliente_nombre", "")):
                    pedido_encontrado = p
                    break
        if pedido_encontrado:
            break
        if intento < intentos - 1:
            print(f"⏳ Pedido no encontrado aún para {telefono}, reintentando ({intento+1}/{intentos})...")
            await asyncio.sleep(espera_segundos)
        
    if pedido_encontrado:
        pedido_id = pedido_encontrado["id"]
        
        # Cambiamos estado a PAGO_POR_VALIDAR
        supabase.table("pedidos").update({"estado": "PAGO_POR_VALIDAR"}).eq("id", pedido_id).execute()
        enviar_mensaje_texto(telefono, "📸 ¡Captura recibida! Estamos validando tu pago. Te avisaremos apenas se confirme y el repartidor vaya en camino.")
        
        # Reiniciar el ciclo del bot para este cliente
        if telefono in SESSION_MEMORY:
            SESSION_MEMORY[telefono] = []
        
        # Le enviamos los botones al Súper Admin y Admins Secundarios para que aprueben
        notificar_a_todos_admins_con_botones(str(pedido_id))
    else:
        enviar_mensaje_texto(telefono, "No tengo ningún pago pendiente por registrar de tu parte. ¿Te puedo ayudar con algo más?")

async def handle_boton(telefono: str, boton_id: str):
    if not supabase: return
    
    es_admin_click = boton_id.startswith("aprobar_") or boton_id.startswith("rechazar_")
    if es_admin_click and not es_administrador(telefono):
        enviar_mensaje_texto(telefono, "❌ No tienes permisos de administrador para realizar esta acción.")
        return
        
    if boton_id.startswith("aprobar_"):
        pedido_id = boton_id.split("_")[1]
        
        # Cambiar a ESPERANDO_DIRECCION
        supabase.table("pedidos").update({"estado": "ESPERANDO_DIRECCION"}).eq("id", pedido_id).execute()
        enviar_mensaje_texto(telefono, f"✅ Has aprobado el pedido #{pedido_id}. Solicitando dirección de entrega al cliente...")
        
        # Notificar al Cliente
        pedido_resp = supabase.table("pedidos").select("*").eq("id", pedido_id).execute()
        if pedido_resp.data:
            pedido = pedido_resp.data[0]
            
            # 1. Notificar al Cliente
            cliente_nombre = pedido.get("cliente_nombre", "")
            if "(" in cliente_nombre and ")" in cliente_nombre:
                telefono_cliente = cliente_nombre.split("(")[-1].split(")")[0]
                enviar_mensaje_texto(telefono_cliente, "✅ ¡Tu pago ha sido confirmado exitosamente! Por favor, envíanos por aquí tu **dirección exacta por escrito** (calle, número de casa, punto de referencia).")
        
    elif boton_id.startswith("rechazar_"):
        pedido_id = boton_id.split("_")[1]
        
        # Cambiar estado nuevamente a ESPERANDO_PAGO para que el cliente mande otra captura
        supabase.table("pedidos").update({"estado": "ESPERANDO_PAGO"}).eq("id", pedido_id).execute()
        enviar_mensaje_texto(telefono, f"❌ Has rechazado la captura del pedido #{pedido_id}. Se le ha notificado al cliente que envíe una nueva captura válida.")
        
        # Notificar al cliente
        pedido_resp = supabase.table("pedidos").select("cliente_nombre").eq("id", pedido_id).execute()
        if pedido_resp.data:
            cliente_nombre = pedido_resp.data[0].get("cliente_nombre", "")
            if "(" in cliente_nombre and ")" in cliente_nombre:
                telefono_cliente = cliente_nombre.split("(")[-1].split(")")[0]
                enviar_mensaje_texto(telefono_cliente, "❌ Hola, ha ocurrido un problema con la validación de tu pago (o la imagen no se ve bien). Por favor, verifica y envía nuevamente la captura de pantalla correcta por aquí para poder procesar tu pedido.")
        
    elif boton_id.startswith("tomar_"):
        pedido_id = boton_id.split("_")[1]
        
        # Verificar si sigue PENDIENTE
        pedido_resp = supabase.table("pedidos").select("*").eq("id", pedido_id).execute()
        if pedido_resp.data:
            pedido = pedido_resp.data[0]
            if pedido["estado"] == "PENDIENTE":
                # Asignarlo
                supabase.table("pedidos").update({"estado": "ASIGNADO", "repartidor_id": telefono}).eq("id", pedido_id).execute()
                
                texto_asignacion = f"✅ ¡Pedido #{pedido_id} asignado a ti!\n\n🏠 Dirección: {pedido.get('direccion', 'N/A')}\n📍 Ubicación GPS: {pedido.get('ubicacion_maps', 'N/A')}"
                enviar_mensaje_texto(telefono, texto_asignacion)
                
                # Avisar al Admin quién lo tomó
                reps = cargar_repartidores()
                datos_rep = reps.get(telefono, {})
                nombre = datos_rep.get("nombre", f"Repartidor {telefono}") if isinstance(datos_rep, dict) else datos_rep
                notificar_a_todos_admins_texto(f"🛵 {nombre} ha tomado el Pedido #{pedido_id} y va en camino a buscarlo al restaurante.")
                
                # Enviar botón de "Recibido en Restaurante" al repartidor
                enviar_boton_recibido(telefono, pedido_id)
            else:
                enviar_mensaje_texto(telefono, "❌ Lo siento, otro repartidor ya tomó este pedido.")

    elif boton_id.startswith("encamino_"):
        pedido_id = boton_id.split("_")[1]
        
        # Marcar en la base de datos como EN_CAMINO
        exito = marcar_pedido_en_camino(int(pedido_id), telefono)
        if exito:
            enviar_mensaje_texto(telefono, f"✅ ¡Perfecto! He notificado al cliente que vas en camino con el pedido #{pedido_id}. ¡Conduce con cuidado!")
            
            # Avisar al Cliente que va en camino
            pedido_resp = supabase.table("pedidos").select("*").eq("id", pedido_id).execute()
            if pedido_resp.data:
                pedido = pedido_resp.data[0]
                cliente_nombre = pedido.get("cliente_nombre", "")
                if "(" in cliente_nombre and ")" in cliente_nombre:
                    telefono_cliente = cliente_nombre.split("(")[-1].split(")")[0]
                    reps = cargar_repartidores()
                    datos_rep = reps.get(telefono, {})
                    nombre = datos_rep.get("nombre", f"Repartidor") if isinstance(datos_rep, dict) else datos_rep
                    enviar_mensaje_texto(telefono_cliente, f"✅ ¡Excelente noticia! Tu pedido acaba de salir del restaurante y va en camino con tu repartidor(a): {nombre}. ¡Prepárate para recibirlo!")
                    
                    # Avisar al Admin que ya el repartidor recogió y va en camino al cliente
                    notificar_a_todos_admins_texto(f"✅ {nombre} ya retiró el Pedido #{pedido_id} del restaurante y va en camino a entregarlo al cliente.")
        else:
            enviar_mensaje_texto(telefono, "❌ Hubo un error al actualizar el estado o este pedido no está asignado a ti.")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

# ============================================================
# TAREA EN SEGUNDO PLANO (ESCALACIÓN DE PEDIDOS SIN REPARTIDOR)
# ============================================================
async def revisar_pedidos_sin_repartidor():
    while True:
        await asyncio.sleep(60)  # Revisar cada minuto
        if not supabase:
            continue
        try:
            pendientes = supabase.table("pedidos").select("*").eq("estado", "PENDIENTE").is_("repartidor_id", "null").eq("alerta_admin_enviada", False).execute()
            ahora = datetime.now(timezone.utc)
            for p in (pendientes.data or []):
                creado = datetime.fromisoformat(p["created_at"])
                minutos_esperando = (ahora - creado).total_seconds() / 60
                if minutos_esperando > 10:
                    notificar_a_todos_admins_texto(
                        f"🚨 URGENTE: Pedido #{p['id']} lleva {int(minutos_esperando)} minutos sin repartidor asignado. Requiere atención manual."
                    )
                    supabase.table("pedidos").update({"alerta_admin_enviada": True}).eq("id", p["id"]).execute()
        except Exception as e:
            print(f"[revisar_pedidos] Error: {e}")

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(revisar_pedidos_sin_repartidor())
