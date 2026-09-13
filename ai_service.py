import os
import json
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# Inicializamos el cliente de Gemini
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def cargar_tarifas_delivery() -> dict:
    if os.path.exists("tarifas_delivery.json"):
        try:
            with open("tarifas_delivery.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error al leer tarifas: {e}")
    # Fallback por defecto si no existe el archivo
    return {"Centro": 2.0, "Norte": 3.0, "Sur": 4.0}

def cargar_metodos_pago() -> dict:
    if os.path.exists("metodos_pago.json"):
        try:
            with open("metodos_pago.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error al leer métodos de pago: {e}")
    # Fallback por defecto leyendo variables de entorno para no exponer PII
    return {
        "pago_movil": {"nombre": "Pago Móvil", "detalles": f"Banco: {os.getenv('PAGO_MOVIL_BANCO', '0102')}, CI: {os.getenv('PAGO_MOVIL_CI', 'V12345678')}, Tlf: {os.getenv('PAGO_MOVIL_TLF', '04140000000')}", "activo": True},
        "zelle": {"nombre": "Zelle", "detalles": f"Correo: {os.getenv('ZELLE_EMAIL', 'pagos@burgerbot.fake')}", "activo": True}
    }

def obtener_prompt_actualizado() -> str:
    tarifas = cargar_tarifas_delivery()
    metodos = cargar_metodos_pago()
    
    seccion_delivery = "### ZONAS DE DELIVERY (TARIFA PLANA)\n"
    for zona, precio in tarifas.items():
        seccion_delivery += f"- {zona} (${precio:.2f})\n"
        
    seccion_pagos = "### DATOS BANCARIOS (SOLO DARLOS AL FINAL)\n"
    for k, v in metodos.items():
        if v.get("activo", True):
            seccion_pagos += f"- {v['nombre']}: {v['detalles']}\n"
            
    return f"""
Eres el asistente virtual experto en ventas de BurgerBot Express, un restaurante de comida rápida.
Tu objetivo principal es tomar los pedidos de los clientes de forma amable, clara y concisa por WhatsApp.

### MENÚ DE COMBOS
- Combo Hamburguesa Clásica ($8.50) - Carne de res 150g, queso, lechuga, tomate, papas regulares y 1 salsa.
- Combo Doble Smash Burger ($12.00) - Doble carne smash, doble queso cheddar, tocineta, papas y 2 salsas.
- Combo Familiar 4 Burgers ($35.00) - 4 hamburguesas clásicas, papas familiares, refresco 2L y 4 salsas.

### ACOMPAÑANTES (SIDES)
- Papas fritas regulares ($3.00)
- Papas con Cheddar y Tocino ($5.00)
- Aros de cebolla ($4.00)

### BEBIDAS
- Refresco 2 Litros ($3.00)
- Refresco de Lata ($1.50)
- Agua Mineral ($1.00)

### EXTRAS Y SALSAS
- Extra de carne ($2.50)
- Salsa BBQ ($0.50)
- Salsa de Ajo ($0.50)

{seccion_delivery}
{seccion_pagos}
### TUS INSTRUCCIONES ESTRICTAS (FLUJO DE VENTAS EN 4 FASES):

Debes comportarte como un vendedor experto, guiando la conversación paso a paso sin abrumar al cliente. ESTÁ ESTRICTAMENTE PROHIBIDO pedir datos antes de confirmar el total de comida.

FASE 1: TOMA DEL PEDIDO Y UP-SELLING SUTIL
- Saluda al cliente y deja que dicte sus platos principales.
- Una vez claro, NO le ofrezcas productos específicos en un solo párrafo gigante. Menciona: "Tenemos productos adicionales como Acompañantes, Bebidas, Extras y Salsas". Pregúntale si desea agregar algo.
- NO pidas NINGÚN DATO en esta fase.

REGLAS ESTRICTAS DE FORMATO PARA WHATSAPP:
- NUNCA uses doble asterisco (**) para negritas. WhatsApp NO lo soporta. Usa SIEMPRE un solo asterisco (*texto*).
- NUNCA escribas párrafos largos. Separa tus oraciones y recomendaciones con saltos de línea y viñetas para que sea fácil de leer en un celular.
- Usa emojis con moderación para que se vea amigable pero profesional.

FASE 2: CIERRE Y CONFIRMACIÓN
- Haz un resumen muy corto y dale el TOTAL estimado (solo de comida).
- Pregunta: "¿Confirmamos tu pedido para proceder a tomar tus datos de envío?". Espera el "Sí".

FASE 3: EXTRACCIÓN DE DATOS
- Únicamente cuando el cliente confirme, pídele amablemente en un solo mensaje: 
  1. Su nombre
  2. Su zona (Tigre, Tigrito o Santome) para calcular el delivery
  3. Método de pago (Efectivo, Pago Móvil o Zelle)
- Recuerda al cliente que la dirección exacta y el link de Google Maps se le pedirán automáticamente justo después de que se valide su pago.

FASE 4: FACTURACIÓN Y COBRO (EL DISPARO FINAL)
- Cuando tengas toda la información, suma el costo del delivery (según su Zona) al total de la comida para darle su **Gran Total a Pagar**.
- Entrégale los Datos Bancarios correspondientes (si eligió Pago Móvil o Zelle).
- Pídele estrictamente: "Por favor, realiza el pago y envíame la **captura de pantalla** por este medio para proceder a despachar".
- INMEDIATAMENTE después de decir eso, DEBES llamar a la herramienta `finalizar_pedido`.
"""

# Definimos la herramienta en formato de Gemini (schema JSON)
finalizar_pedido_tool = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="finalizar_pedido",
            description="Se ejecuta ÚNICAMENTE en la FASE 4, cuando el cliente ya dio su nombre, zona y método de pago, y le has dado el Gran Total a pagar y los datos bancarios.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "cliente_nombre": types.Schema(type=types.Type.STRING),
                    "zona_delivery": types.Schema(type=types.Type.STRING, description="Centro, Norte o Sur"),
                    "metodo_pago": types.Schema(type=types.Type.STRING, description="Ej: Efectivo, Pago Móvil, Zelle"),
                    "items": types.Schema(
                        type=types.Type.ARRAY,
                        items=types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "producto": types.Schema(type=types.Type.STRING),
                                "cantidad": types.Schema(type=types.Type.INTEGER)
                            },
                            required=["producto", "cantidad"]
                        )
                    ),
                    "total_comida": types.Schema(type=types.Type.NUMBER),
                    "costo_delivery": types.Schema(type=types.Type.NUMBER),
                    "gran_total": types.Schema(type=types.Type.NUMBER, description="Suma de comida + delivery")
                },
                required=["cliente_nombre", "zona_delivery", "metodo_pago", "items", "total_comida", "costo_delivery", "gran_total"]
            )
        )
    ]
)

def obtener_respuesta_ia(historial: list) -> dict:
    """
    Envía el historial de la conversación a Gemini y devuelve un diccionario con texto o llamado a herramienta.
    """
    # Convertir historial general al formato Content de Gemini
    gemini_history = []
    for msg in historial:
        role = "user" if msg["role"] == "user" else "model"
        gemini_history.append(
            types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])])
        )
    
    # Configuramos el modelo de Gemini con el prompt actualizado dinámicamente
    prompt_actualizado = obtener_prompt_actualizado()
    config = types.GenerateContentConfig(
        system_instruction=prompt_actualizado,
        temperature=0.3,
        tools=[finalizar_pedido_tool]
    )

    try:
        response = client.models.generate_content(
            model="gemini-flash-lite-latest",
            contents=gemini_history,
            config=config
        )
        
        # Revisamos si Gemini decidió usar la herramienta
        if response.function_calls:
            tool_call = response.function_calls[0]
            if tool_call.name == "finalizar_pedido":
                argumentos_json = tool_call.args
                # args suele ser un diccionario en la nueva versión de SDK
                if isinstance(argumentos_json, str):
                    argumentos_json = json.loads(argumentos_json)
                return {"tipo": "pedido_completado", "contenido": argumentos_json}
        
        # Si no hubo llamada a herramienta, enviamos el texto de respuesta
        return {"tipo": "texto", "contenido": response.text or ""}
    except Exception as e:
        print(f"Error con Gemini API: {e}")
        return {"tipo": "texto", "contenido": "Hubo un error al procesar tu respuesta con nuestra IA. Por favor, intenta de nuevo."}

