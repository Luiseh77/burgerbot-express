import os
import sys
import json
import asyncio
from fastapi import FastAPI, Request, HTTPException, Query, BackgroundTasks
from fastapi.responses import PlainTextResponse
import uvicorn
from dotenv import load_dotenv
from datetime import datetime, timezone

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

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "")
ADMIN_PHONE = os.getenv("ADMIN_PHONE", "")

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
    if ADMIN_PHONE:
        enviar_botones_aprobacion(ADMIN_PHONE, pedido_id)
    admins = cargar_administradores()
    for admin_tel in admins.keys():
        enviar_botones_aprobacion(admin_tel, pedido_id)

def notificar_a_todos_admins_texto(mensaje: str):
    if ADMIN_PHONE:
        enviar_mensaje_texto(ADMIN_PHONE, mensaje)
    admins = cargar_administradores()
    for admin_tel in admins.keys():
        enviar_mensaje_texto(admin_tel, mensaje)


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
                    pendientes = supabase.table("pedidos").select("*").eq("estado", "PENDIENTE").is_("repartidor_id", "null").execute()
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
        response = supabase.table("pedidos").select("*").eq("estado", "ESPERANDO_PAGO").execute()
        tiene_pendiente = any(telefono in str(p.get("cliente_nombre", "")) for p in (response.data or []))
        if tiene_pendiente:
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

    # 2. Si no está esperando pago, es un chat normal con la IA
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
        
        # Inject phone number into name to track it without altering DB schema
        nombre_original = datos_pedido.get('cliente_nombre', 'Cliente')
        datos_pedido["cliente_nombre"] = f"{nombre_original} ({telefono})"
        
        # Guardar el teléfono real en la nueva columna de DB
        datos_pedido["telefono"] = telefono
        
        # Guardar en DB con estado ESPERANDO_PAGO
        resultado = guardar_pedido_nuevo(datos_pedido)
        if resultado:
            print(f"💾 Pedido {resultado['id']} guardado. Esperando pago.")
            
            # Mensaje de cobro generado por el código usando datos reales del DB
            tasa_actual = obtener_tasa_bcv()
            total_usd = float(resultado.get('total', 0))
            total_bs = round(total_usd * tasa_actual, 2)
            metodos = cargar_metodos_pago()
            metodo_cliente = datos_pedido.get('metodo_pago', '').lower()
            
            detalles_pago = ""
            key_encontrada = None
            for k, v in metodos.items():
                if v.get("activo", True) and (k.replace("_", " ") in metodo_cliente or v["nombre"].lower() in metodo_cliente):
                    key_encontrada = k
                    detalles_pago = v["detalles"]
                    break
            if not detalles_pago:
                detalles_pago = "Métodos disponibles:\n"
                for k, v in metodos.items():
                    if v.get("activo", True):
                        detalles_pago += f"- *{v['nombre']}*: {v['detalles']}\n"
                        
            texto_cobro = (
                f"¡Excelente {nombre_original}!\n\n"
                f"Tu pedido está confirmado. El Gran Total a pagar es: *${total_usd}*\n"
                f"*(Equivalente a {total_bs} Bs según tasa BCV de {tasa_actual})*\n\n"
                "Por favor, realiza tu pago y envíame por aquí la *captura de pantalla* del comprobante.\n\n"
                f"Instrucciones de Pago:\n{detalles_pago}"
            )
            enviar_mensaje_texto(telefono, texto_cobro)
            
            # Enviar formato pegable de Pago Móvil en mensaje separado
            if key_encontrada == "pago_movil" or "movil" in metodo_cliente or "móvil" in metodo_cliente:
                pm = metodos.get("pago_movil", {})
                if not pm:
                    print("⚠️ Método pago_movil no configurado en metodos_pago.json")
                else:
                    banco = pm.get("banco", "")
                    tlf = pm.get("telefono", "")
                    ced = pm.get("cedula", "")
                    monto_formateado = f"{total_bs:.2f}".replace(".", ",")
                    enviar_mensaje_texto(telefono, f"Banco: {banco}\nTeléfono: {tlf}\nCédula: {ced}\nMonto: {monto_formateado} Bs")
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
#   = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =  
 #   T A R E A   E N   S E G U N D O   P L A N O   ( E S C A L A C I O N   D E   P E D I D O S )  
 #   = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =  
 a s y n c   d e f   r e v i s a r _ p e d i d o s _ s i n _ r e p a r t i d o r ( ) :  
         w h i l e   T r u e :  
                 a w a i t   a s y n c i o . s l e e p ( 6 0 )  
                 i f   n o t   s u p a b a s e :   c o n t i n u e  
                 p e n d i e n t e s   =   s u p a b a s e . t a b l e ( ' p e d i d o s ' ) . s e l e c t ( ' * ' ) . e q ( ' e s t a d o ' ,   ' P E N D I E N T E ' ) . i s _ ( ' r e p a r t i d o r _ i d ' ,   ' n u l l ' ) . e q ( ' a l e r t a _ a d m i n _ e n v i a d a ' ,   F a l s e ) . e x e c u t e ( )  
                 a h o r a   =   d a t e t i m e . n o w ( t i m e z o n e . u t c )  
                 f o r   p   i n   ( p e n d i e n t e s . d a t a   o r   [ ] ) :  
                         c r e a d o   =   d a t e t i m e . f r o m i s o f o r m a t ( p [ ' c r e a t e d _ a t ' ] )  
                         m i n u t o s _ e s p e r a n d o   =   ( a h o r a   -   c r e a d o ) . t o t a l _ s e c o n d s ( )   /   6 0  
                         i f   m i n u t o s _ e s p e r a n d o   >   1 0 :  
                                 n o t i f i c a r _ a _ t o d o s _ a d m i n s _ t e x t o ( f ' =ب�  U R G E N T E :   P e d i d o   # { p [ \  
 i d \ ] }   l l e v a   { i n t ( m i n u t o s _ e s p e r a n d o ) }   m i n u t o s   s i n   r e p a r t i d o r   a s i g n a d o .   R e q u i e r e   a t e n c i � n   m a n u a l . ' )  
                                 s u p a b a s e . t a b l e ( ' p e d i d o s ' ) . u p d a t e ( { ' a l e r t a _ a d m i n _ e n v i a d a ' :   T r u e } ) . e q ( ' i d ' ,   p [ ' i d ' ] ) . e x e c u t e ( )  
  
 @ a p p . o n _ e v e n t ( ' s t a r t u p ' )  
 a s y n c   d e f   s t a r t u p _ e v e n t ( ) :  
         a s y n c i o . c r e a t e _ t a s k ( r e v i s a r _ p e d i d o s _ s i n _ r e p a r t i d o r ( ) )  
 