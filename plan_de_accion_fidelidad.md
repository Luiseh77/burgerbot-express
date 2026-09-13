# Plan de Acción: Perfil de Cliente, Puntos de Fidelidad y Tarifas Dinámicas (BurgerBot Express)

Este documento detalla el diseño técnico para implementar el **Sistema de Fidelidad**, la **Autodetección de Clientes Frecuentes**, y la **Configuración Dinámica de Tarifas por Zona** (Tigre, Tigrito, Santome) para que el dueño del restaurante pueda ajustar los precios de delivery en cualquier momento.

---

## 1. Estructura de la Base de Datos Ampliada (Supabase)
Para registrar tanto los puntos como los datos históricos de dirección y nombre del cliente, ejecuta este script en el **SQL Editor** de Supabase:

```sql
-- Crear tabla de clientes con perfil completo e histórico
CREATE TABLE IF NOT EXISTS clientes (
    telefono TEXT PRIMARY KEY,          -- Número de WhatsApp (ej: "584121234567")
    nombre TEXT,                        -- Nombre guardado
    zona_delivery TEXT,                 -- Zona de delivery guardada (Tigre, Tigrito, Santome)
    direccion TEXT,                     -- Dirección detallada guardada
    ubicacion_maps TEXT,                -- Enlace de Google Maps
    puntos INTEGER DEFAULT 0,           -- Puntos actuales para canjear
    puntos_historico INTEGER DEFAULT 0,  -- Total acumulado históricamente
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Otorgar permisos a la API de Supabase
ALTER TABLE clientes ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Permitir lectura y escritura a service_role" 
ON clientes TO service_role USING (true) WITH CHECK (true);
```

---

## 2. Archivo de Configuración de Fidelidad (`fidelidad_config.json`)
Este archivo controla la relación de puntos y los premios activos del local:

```json
{
  "puntos_por_dolar": 1.0,
  "premios": [
    {
      "id": "refresco_gratis",
      "nombre": "Refresco de 1.5 Litros Gratis",
      "puntos_requeridos": 15
    },
    {
      "id": "delivery_gratis",
      "nombre": "Delivery Gratis",
      "puntos_requeridos": 20
    },
    {
      "id": "hamburguesa_gratis",
      "nombre": "Hamburguesa Clásica Gratis",
      "puntos_requeridos": 50
    }
  ]
}
```

---

## 3. Archivo de Configuración de Tarifas de Delivery (`tarifas_delivery.json`) [NUEVO]
Para evitar dejar las tarifas fijas en el código de la Inteligencia Artificial, crearemos este archivo de configuración en la raíz del proyecto. El dueño del restaurante podrá editar estos valores cuando lo requiera:

```json
{
  "Tigre": 2.00,
  "Tigrito": 3.00,
  "Santome": 4.00
}
```

---

## 4. Lógica de Flujo: Autodetectar Cliente y Tarifas Dinámicas

### A. Carga de Tarifas y Prompt Dinámico (`ai_service.py`)
Modificaremos `ai_service.py` para leer `tarifas_delivery.json` en tiempo de ejecución. De esta manera, si cambian las tarifas en el archivo JSON, la IA automáticamente conocerá los nuevos precios en el siguiente mensaje, sin necesidad de reprogramar:

```python
# Función para cargar tarifas dinámicas
def cargar_tarifas_delivery() -> dict:
    if os.path.exists("tarifas_delivery.json"):
        try:
            with open("tarifas_delivery.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error al leer tarifas: {e}")
    # Fallback por defecto si no existe el archivo
    return {"Tigre": 2.0, "Tigrito": 3.0, "Santome": 4.0}

def obtener_prompt_actualizado() -> str:
    tarifas = cargar_tarifas_delivery()
    
    # Construir la sección de zonas con las tarifas reales del JSON
    seccion_delivery = "### ZONAS DE DELIVERY (TARIFA PLANA)\n"
    for zona, precio in tarifas.items():
        seccion_delivery += f"- {zona} (${precio:.2f})\n"
        
    # El prompt base ahora es dinámico e incluye la sección generada
    prompt_base = f"""
    Eres el asistente virtual experto en ventas de BurgerBot Express...
    
    {seccion_delivery}
    
    ### DATOS BANCARIOS (SOLO DARLOS AL FINAL)...
    """
    return prompt_base
```
*En `obtener_respuesta_ia(historial)`, la variable `system_instruction` se asignará llamando a `obtener_prompt_actualizado()`.*

---

### B. Preparación del Historial para la IA (`main.py` -> `handle_texto`)
Al enviarle el chat a Gemini en `handle_texto`, inyectamos una **Nota de Sistema** si detectamos que el cliente ya compró antes, indicándole a Gemini que no pida los datos de cero:

```python
# Buscar perfil del cliente en base de datos
from db_service import obtener_o_crear_cliente
perfil_cliente = obtener_o_crear_cliente(telefono, "Cliente")

# Crear nota del sistema si el cliente ya tiene datos guardados
nota_perfil = ""
if perfil_cliente and perfil_cliente.get("direccion"):
    nota_perfil = (
        f"[INFORMACIÓN DEL SISTEMA]: Este cliente es recurrente. "
        f"Su nombre guardado es '{perfil_cliente['nombre']}', su dirección es '{perfil_cliente['direccion']}' "
        f"en la zona '{perfil_cliente['zona_delivery']}' y su ubicación GPS es '{perfil_cliente['ubicacion_maps']}'. "
        f"En la FASE 3 de toma de datos, NO le pidas estos datos de nuevo. Pregúntale amablemente: "
        f"'¿Confirmamos tu pedido para enviarlo a tu dirección habitual en {perfil_cliente['direccion']}?' "
        f"Solo si el cliente te dice que está en otro lugar o quiere cambiar sus datos, procedes a pedirle la nueva información."
    )

# Insertar esta nota como el primer mensaje del sistema en el historial enviado a obtener_respuesta_ia
historial_con_perfil = []
if nota_perfil:
    historial_con_perfil.append({"role": "system", "content": nota_perfil})
```

---

### C. Modificaciones en la Aprobación del Pedido (`main.py` -> `handle_boton` -> `aprobar_`)
Al aprobar el pago, además de sumar puntos, **guardamos la dirección del pedido actual como su dirección habitual** en la tabla `clientes`:

```python
# Al aprobar el pedido:
# 1. Extraemos los datos que guardó Gemini en la tabla "pedidos"
direccion_completa = pedido["direccion"] # Formato: "Zona: Tigre | Calle 5..."
zona = direccion_completa.split("|")[0].replace("Zona: ", "").strip()
direccion_detallada = direccion_completa.split("|")[1].strip() if "|" in direccion_completa else direccion_completa

# 2. Actualizamos el perfil en Supabase
from db_service import actualizar_perfil_cliente
actualizar_perfil_cliente(
    telefono=telefono_cliente,
    nombre=nombre_limpio,
    zona=zona,
    direccion=direccion_detallada,
    maps_link=pedido["ubicacion_maps"]
)
```

---

## 5. Resumen del Flujo de Usuario con Tarifas Dinámicas
1. **El administrador del restaurante** puede cambiar el precio de delivery en `tarifas_delivery.json` en cualquier momento (ej: Tigre sube a $2.50).
2. **El bot de WhatsApp** lee el archivo de inmediato. Cuando un cliente pregunta por el precio a Tigre, la IA responde con $2.50 automáticamente.
3. Si el cliente es frecuente, el sistema recupera sus datos históricos y calcula el total sumando el nuevo precio de delivery dinámico según su zona guardada, ahorrando pasos de confirmación.
