import os
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "")

def get_url():
    return f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"

def get_headers():
    return {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

def enviar_mensaje_texto(destino_telefono: str, texto: str):
    """Envía un mensaje de texto simple a través de WhatsApp"""
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        print("⚠️ Faltan tokens de WhatsApp en el .env")
        return None
        
    data = {
        "messaging_product": "whatsapp",
        "to": destino_telefono,
        "type": "text",
        "text": {"body": texto}
    }
    response = requests.post(get_url(), headers=get_headers(), json=data)
    print(f"📤 Respuesta de Meta ({destino_telefono}): Código {response.status_code} | {response.text}")
    return response.json()

def enviar_botones_aprobacion(admin_telefono: str, pedido_id: str):
    """Envía un mensaje con botones interactivos al Dueño/Admin para aprobar un pago"""
    if not admin_telefono: return
    data = {
        "messaging_product": "whatsapp",
        "to": admin_telefono,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": f"🚨 ¡NUEVO PAGO RECIBIDO! 🚨\n\nEl cliente ha enviado la captura del Pedido #{pedido_id}.\nPor favor verifica tu cuenta bancaria.\n\n¿El dinero está efectivo?"
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": f"aprobar_{pedido_id}",
                            "title": "✅ Aprobar Pago"
                        }
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": f"rechazar_{pedido_id}",
                            "title": "❌ Rechazar"
                        }
                    }
                ]
            }
        }
    }
    response = requests.post(get_url(), headers=get_headers(), json=data)
    print(f"📤 Respuesta de Meta (Botones ADMIN {admin_telefono}): Código {response.status_code} | {response.text}")
    return response.json()

def enviar_broadcast_deliverys(deliverys: list, pedido_id: str, zona: str, gran_total: float):
    """Envía un mensaje con botón a la lista de repartidores para que uno lo tome"""
    for delivery in deliverys:
        if not delivery.strip(): continue
        data = {
            "messaging_product": "whatsapp",
            "to": delivery.strip(),
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {
                    "text": f"🛵 ¡NUEVO PEDIDO LISTO PARA ENTREGAR! 🛵\n\nZona: {zona}\nCobro Total: ${gran_total}\n\n¿Quién lo toma?"
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": f"tomar_{pedido_id}",
                                "title": "🤚 ¡Yo lo llevo!"
                            }
                        }
                    ]
                }
            }
        }
        response = requests.post(get_url(), headers=get_headers(), json=data)
        print(f"📤 Respuesta de Meta (Broadcast Delivery {delivery}): Código {response.status_code} | {response.text}")

def enviar_boton_recibido(repartidor_telefono: str, pedido_id: str):
    """Envía un mensaje con botón al repartidor para confirmar que ya recogió el pedido"""
    if not repartidor_telefono: return
    data = {
        "messaging_product": "whatsapp",
        "to": repartidor_telefono.strip(),
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": f"📍 Cuando recibas el pedido #{pedido_id} en el restaurante, presiona el botón para notificar al cliente que vas en camino."
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": f"encamino_{pedido_id}",
                            "title": "✅ Recibido"
                        }
                    }
                ]
            }
        }
    }
    response = requests.post(get_url(), headers=get_headers(), json=data)
    print(f"📤 Respuesta de Meta (Botón Recibido a {repartidor_telefono}): Código {response.status_code} | {response.text}")
