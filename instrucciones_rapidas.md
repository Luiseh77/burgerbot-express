# 🚀 Instrucciones Rápidas para Probar el Bot (Mañana)

Sigue estos pasos rápidos en tu terminal para encender y probar el bot en esta nueva ubicación.

---

## 1. Configurar y Activar el Entorno (Solo se hace la primera vez)
Abre tu terminal (PowerShell o CMD) en esta carpeta y ejecuta:

```bash
# A. Crear el entorno virtual
python -m venv venv

# B. Activar el entorno virtual
# Si usas PowerShell:
.\venv\Scripts\Activate.ps1
# Si usas CMD:
.\venv\Scripts\activate.bat

# C. Instalar dependencias
pip install -r requirements.txt
```

---

## 2. Verificar Variables de Entorno (`.env`)
Asegúrate de que tu archivo `.env` en esta carpeta tenga los tokens actualizados:
* `GEMINI_API_KEY`: Tu clave de Google AI Studio.
* `SUPABASE_URL` y `SUPABASE_KEY`: Enlace a tu base de datos Supabase.
* `ADMIN_PHONE`: Tu número de teléfono para recibir alertas de repartidores y validación de cobros.
* `WHATSAPP_TOKEN`: El token temporal de Meta (recuerda que dura 24 horas en modo prueba).

---

## 3. Encender el Servidor
Con el entorno virtual activo `(venv)`, inicia el servidor de FastAPI:

```bash
python main.py
```
*El servidor correrá en: `http://localhost:8000`*

---

## 4. Encender el Túnel (Ngrok / Serveo)
El webhook de Meta necesita una dirección HTTPS pública para comunicarse con tu PC local.

* **Opción Ngrok:**
  ```bash
  ngrok http 8000
  ```
* **Opción Serveo (sin instalar nada):**
  ```bash
  ssh -R 80:localhost:8000 serveo.net
  ```
*Copia la URL segura `https://...` generada y actualízala en el panel de **Meta Developers -> WhatsApp -> Configuración de Webhooks -> URL de devolución de llamada**.*

---

## 5. ¡A Probar!
* Escribe un mensaje de prueba al número de WhatsApp del bot (ej: *"Hola, quiero ver el menú"*).
* Verifica la consola de FastAPI para ver las solicitudes entrantes en tiempo real.
