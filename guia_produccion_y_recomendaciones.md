# Guía de Producción y Recomendaciones - BurgerBot Express Bot

Esta guía resume todas las recomendaciones de arquitectura, estrategias de cobro, comparativas tecnológicas y planes de seguridad discutidos para el lanzamiento comercial del bot de WhatsApp.

---

## 1. Estrategia de Negocio y Monetización
Para vender este bot a restaurantes de manera exitosa y sostenible, te recomiendo el esquema de **SaaS (Software como Servicio)**:

### Esquema de Cobro Recomendado
1. **Costo de Configuración Inicial (Setup Fee):** 
   * **Monto sugerido:** $100 - $250 USD (pago único).
   * **¿Qué cubre?:** Carga inicial de su menú, configuración del número de WhatsApp en Meta, conexión de sus cuentas de pago (Pago Móvil/Zelle) y entrenamiento del bot con las reglas específicas de su local.
2. **Mensualidad por Mantenimiento y Servidores:**
   * **Monto sugerido:** $30 - $60 USD al mes.
   * **¿Qué cubre?:** Alojamiento del bot en la nube, base de datos Supabase, soporte técnico si cambian precios/platos del menú, y uso de la inteligencia artificial.

### Costos Operativos Estimados para Ti (Por Restaurante)
* **Alojamiento (Render / Railway / VPS):** ~$5 a $7 USD al mes.
* **Base de Datos (Supabase):** Gratis (el plan gratuito sobra para el flujo de un restaurante individual).
* **API de Meta (WhatsApp):** Gratis las primeras 1,000 conversaciones del mes. Si el restaurante supera las 1,000 conversaciones, Meta cobra aprox. $0.01 a $0.02 USD por conversación iniciada por cliente (el mismo restaurante cubre esto con su mensualidad o se le cobra un excedente).
* **API de Gemini:** Gratis en la versión de desarrollo; en la versión de pago por uso (si escala mucho), el costo es insignificante (menos de $1 o $2 USD al mes por volumen estándar de pedidos).
* **Margen de Ganancia Neto:** ~80% a 90% mensual por cliente.

---

## 2. Nube vs. Local (Recomendación para Venezuela)
Para el contexto de Venezuela, es **indispensable** utilizar una infraestructura 100% en la nube:

* **Sin interrupción por luz/internet:** Al estar alojado en servidores externos (nube), si el restaurante se queda sin luz o internet, el bot en WhatsApp **sigue respondiendo al cliente**. El pedido queda procesado y guardado en Supabase. El restaurante verá las comandas acumuladas apenas recupere su conexión.
* **Sin gastos en hardware:** Un servidor local rápido requiere una GPU dedicada cara (tarjeta de video Nvidia de más de $1,000 USD). En la nube, usamos la infraestructura de Google (Gemini) de forma remota, reduciendo el costo inicial a cero.
* **Concurrencia:** La nube puede atender a 50 clientes ordenando simultáneamente sin retrasos. Una computadora local se saturaría rápidamente haciendo esperar a los clientes.

---

## 3. Seguridad y Prevención de Spam (Usuarios Maliciosos)
Para evitar que personas malintencionadas "saturen" el bot o inflen los costos de la IA, aplicamos las siguientes estrategias en producción:

### Facturación Protegida (Meta)
* Meta cobra por **ventana de conversación de 24 horas**, no por mensajes enviados.
* Si alguien escribe 5,000 mensajes molestando en un solo día, Meta solo te cobrará **1 conversación** en tu factura mensual.

### Medidas en el Código
1. **Sistema de Lista Negra (Blacklist):**
   * Crearemos una tabla o archivo (`bloqueados.json` / tabla Supabase) controlado por comandos de administrador (ej: `BLOQUEAR 584140000000`).
   * Si un número está en la lista negra, el bot ignora por completo sus mensajes entrantes en el webhook, evitando consumir tokens de Gemini o cargar la base de datos.
2. **Límites de Ritmo (Rate Limiting):**
   * Configurar el servidor para que ignore mensajes si un mismo número envía más de 5 mensajes en menos de 30 segundos (evita ataques con bots automatizados).
3. **Filtro de Estado:**
   * Si un usuario escribe más de 10 mensajes seguidos sin avanzar en el proceso del pedido, el bot suspende temporalmente su sesión por 1 hora.

---

## 4. Paso a Paso para el Lanzamiento a Producción

Cuando decidas desplegar el bot real para un cliente:

### Paso 1: Configurar Meta Business Suite
1. Entra a [Meta for Developers](https://developers.facebook.com/) con la cuenta comercial del restaurante (debe ser una empresa verificada o tener una cuenta publicitaria activa).
2. Crea una aplicación de tipo **Business** o **Negocios**.
3. Añade el servicio de **WhatsApp**.

### Paso 2: Configurar el Número Real
1. Compra una tarjeta SIM/Línea telefónica nueva destinada únicamente al bot.
2. **¡IMPORTANTE!:** No registres este número en un teléfono con la app de WhatsApp normal ni WhatsApp Business. Debe estar libre de aplicaciones móviles para que la API de Meta pueda tomar el control.
3. En el panel de Meta, registra este número de teléfono mediante llamada o SMS de verificación.

### Paso 3: Despliegue en la Nube
1. Sube tu código de FastAPI a una plataforma en la nube como **Render.com** o un **VPS de Hostinger/Hetzner**.
2. Configura las variables de entorno (`.env`):
   * `WHATSAPP_TOKEN`: El token de acceso permanente de producción (Meta lo provee al verificar el negocio).
   * `GEMINI_API_KEY`: Tu clave de Google AI Studio.
   * `SUPABASE_URL` y `SUPABASE_KEY`: Tus credenciales de la base de datos de producción.
3. Configura el Webhook en el panel de Meta apuntando a la dirección HTTPS de tu servidor en la nube (ej: `https://tu-servidor.com/webhook`).

### Paso 4: Pruebas Iniciales
* Escribe desde cualquier teléfono no registrado previamente. El bot ya debería responder y guiarte a través del menú de forma abierta.
