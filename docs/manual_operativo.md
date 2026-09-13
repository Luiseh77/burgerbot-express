# 📖 Manual Operativo de BurgerBot Express

Este documento explica paso a paso cómo se usa el sistema en el día a día desde la perspectiva de las tres personas involucradas: el Cliente, el Administrador y el Repartidor.

---

## 1. Para el Cliente (Cómo pedir comida)

El bot atiende al cliente de forma natural, como si fuera un humano. El flujo de una compra típica se ve así:

*   **Cliente:** "Hola, buenas noches. ¿Tienen hamburguesas?"
*   **BurgerBot:** "¡Hola! Bienvenidos a BurgerBot Express 🍔. Sí, claro. Tenemos la *Classic Burger* ($5) y la *Double Smash Burger* ($8). Ambas vienen en combos con papas y refresco. ¿Qué te provoca hoy?"
*   **Cliente:** "Quiero un combo Double Smash, por favor."
*   **BurgerBot:** "¡Excelente elección! Serían $10 en total (incluyendo el combo). ¿Deseas agregar alguna salsa extra o postre antes de cerrar tu orden?"
*   **Cliente:** "No, así está bien."
*   **BurgerBot:** "Perfecto. Para calcular el envío, ¿a qué zona te enviamos tu pedido?"
*   **Cliente:** "Zona Norte."
*   **BurgerBot:** "El delivery a la Zona Norte cuesta $2. Tu Gran Total es de $12. Puedes pagar por Zelle a `pagos@burgerbot.fake` o por Pago Móvil. Por favor, pásame la foto de la transferencia por aquí."
*   **Cliente:** *(Envía la foto de la captura de pantalla del pago).*
*   **BurgerBot:** "📸 ¡Captura recibida! Estamos validando tu pago. Te avisaremos apenas el repartidor vaya en camino."

*(Una vez que el administrador aprueba, el bot le vuelve a escribir al cliente).*
*   **BurgerBot:** "¡Excelente! Tu pedido está confirmado. Ya un repartidor va en camino."

---

## 2. Para el Administrador (Dueño/Cajero)

Tu rol es verificar que el dinero de los pagos realmente haya entrado al banco y monitorear al equipo.

**Aprobar o Rechazar Pagos**
*   Cuando un cliente sube la foto de su transferencia, el bot **no** la aprueba por sí solo. 
*   Inmediatamente recibirás un mensaje de WhatsApp del bot diciendo: *"🚨 ¡NUEVO PAGO RECIBIDO! El cliente ha enviado la captura... ¿El dinero está efectivo?"*
*   El mensaje vendrá con dos botones: **✅ Aprobar Pago** y **❌ Rechazar**.
*   Revisa tu cuenta de banco real. Si el dinero está ahí, toca "Aprobar". En ese instante, el bot despacha la orden a los repartidores.

**Control de Asistencia del Staff**
*   Para saber quiénes de tus repartidores están trabajando hoy, escríbele al bot la palabra: **DISPONIBLES** (o "quien esta activo").
*   El bot te responderá con una lista detallada mostrando quiénes ya iniciaron su turno (y a qué hora lo hicieron) y te marcará con una ❌ quiénes faltan por reportarse.
*   *Nota: Si ves que un repartidor no aparece activo, contáctalo por llamada o chat personal para recordarle que debe saludar al bot, de lo contrario no podrá recibir los pedidos.*

**Administrar Repartidores (Directo desde WhatsApp)**
Como administrador, puedes agregar o eliminar motorizados escribiendo comandos exactos al bot:
*   Para agregar uno nuevo: Escribe `AGREGAR REPARTIDOR 584120000000 Nombre del Motorizado` (Siempre usa el código de país sin el +).
*   Para eliminar uno existente: Escribe `ELIMINAR REPARTIDOR 584120000000`.
*   Para ver la lista de tu equipo: Escribe `VER REPARTIDORES`.

**Configuraciones Adicionales**
*   Tasa del dólar: El bot lee la tasa oficial del BCV por internet. Si falla, puedes forzar una manualmente escribiendo: `FIJAR TASA 38.50`. Para borrarla y volver al BCV, escribe `BORRAR TASA`.
*   Métodos de pago: Puedes modificar los datos de pago escribiendo `AGREGAR PAGO id Nombre | Detalles`. Por ejemplo: `AGREGAR PAGO zelle Zelle | pagozelle@midelivery.com`. Para verlos todos usa `VER PAGOS`.

---

## 3. Para el Repartidor (Motorizado)

**Inicio de Turno (Súper Importante)**
*   Todos los días, justo cuando empieces a trabajar, **debes enviarle un mensaje al bot** (puedes decirle "Hola", "Activo" o enviar un emoji).
*   **¿Por qué?** WhatsApp tiene una regla estricta de seguridad: si no le has escrito al bot en todo el día, el bot tiene "prohibido" hablarte. Al saludarlo en la mañana, le das "permiso" para que te envíe notificaciones de pedidos nuevos durante toda tu jornada.

**Tomar un Pedido**
*   Cuando el administrador aprueba un pago, el bot envía un mensaje al mismo tiempo a todos los repartidores activos: *"🛵 ¡NUEVO PEDIDO LISTO PARA ENTREGAR! Zona Norte. ¿Quién lo toma?"*
*   Este mensaje tiene un botón: **"🤚 ¡Yo lo llevo!"**.
*   Si eres el primero en presionar el botón, el pedido es tuyo. El bot te avisará que te lo asignó exitosamente.

**Recoger el Pedido**
*   Cuando el bot te asigna el pedido, te envía un nuevo botón que dice: **"✅ Recibido"**.
*   Una vez que vayas al restaurante, recojas la bolsa de comida y te montes en la moto, presiona ese botón. 
*   Al hacerlo, el bot le enviará automáticamente un mensaje al cliente avisándole que tú (con tu nombre) ya vas en camino hacia su casa.

---

## 4. Preguntas Frecuentes

**¿Qué pasa si dos repartidores presionan el botón "¡Yo lo llevo!" casi al mismo tiempo?**
No hay problema. El sistema es tan rápido que registrará al que lo tocó una fracción de segundo antes. Al primero le dirá que el pedido es suyo, y al segundo le enviará un mensaje automático diciendo: *"❌ Lo siento, otro repartidor ya tomó este pedido"*. Nunca se asignará un mismo pedido a dos personas.

**¿Qué pasa si un repartidor olvida saludar al bot en la mañana?**
No aparecerá en la lista de "DISPONIBLES" del administrador y, lo más crítico, **no recibirá los mensajes de nuevos pedidos** porque WhatsApp bloqueará los mensajes del bot hacia su número. Tan pronto se dé cuenta, solo debe decirle "Hola" al bot y empezará a recibir los pedidos nuevamente.

**¿Qué pasa si la página oficial del dólar (BCV) se cae o falla?**
El bot intentará conectarse a la página oficial. Si no responde en 5 segundos, el bot no se va a colgar ni va a dejar de vender. Automáticamente usará una "tasa de emergencia" (fijada por el administrador previamente) para asegurar que el cliente siempre reciba el cálculo correcto en Bolívares y pueda pagar sin demoras.
