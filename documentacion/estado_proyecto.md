# 📋 Estado del Proyecto y Checklist - BurgerBot Express Bot

Este documento sirve como el centro de control del proyecto para verificar los puntos completados y los que aún están pendientes de implementar.

---

## 🚀 Checklist General de Funcionalidades

### ✅ 1. Infraestructura y Conexión Base
- [x] Servidor FastAPI configurado e instalado localmente.
- [x] Configuración de variables de entorno `.env` (Gemini, Supabase, Meta, Administrador).
- [x] Creación del túnel seguro de Webhook automático con re-conexión (Serveo).
- [x] Validación y verificación del webhook exitosa en Meta Developers.
- [x] Suscripción correcta al evento de mensajes (`messages`) en WhatsApp.
- [x] Corrección del bug de reintentos (Webhook loops) usando `BackgroundTasks` para responder instantáneamente `200 OK` a Meta.

### ✅ 2. Flujo del Bot y Procesamiento con IA
- [x] Integración de Gemini API para comprender el chat.
- [x] Definición del prompt en 4 fases (Toma de pedido, Confirmación, Datos, Facturación).
- [x] Extracción estructurada del pedido usando herramientas de Gemini (`finalizar_pedido`).
- [x] Envío de mensaje final de cobro detallado con montos.
- [x] Consulta de tasa BCV en tiempo real e integración de tasa manual para el cobro.

### ✅ 3. Comandos de Administración por WhatsApp
- [x] Agregar repartidores a la libreta (`AGREGAR REPARTIDOR`).
- [x] Eliminar repartidores de la libreta (`ELIMINAR REPARTIDOR`).
- [x] Ver lista de repartidores (`VER REPARTIDORES`).
- [x] Fijar tasa manual por WhatsApp (`FIJAR TASA`).
- [x] Volver a tasa automática (`BORRAR TASA`).

### ✅ 4. Métodos de Pago Dinámicos
- [x] Crear archivo de almacenamiento `metodos_pago.json` para gestionar cuentas de cobro.
- [x] Modificar `ai_service.py` para cargar los métodos de pago dinámicos en el prompt del sistema.
- [x] Crear comandos de administrador para gestionar pagos desde WhatsApp (`VER PAGOS`, `AGREGAR PAGO`, `ELIMINAR PAGO`, `ACTIVAR PAGO`, `DESACTIVAR PAGO`).
- [x] Actualizar el mensaje de cobro final para renderizar las cuentas bancarias de manera dinámica.

---

## 🛠️ Puntos Pendientes (Por Implementar)

### ⏳ Fase B: Historial y Perfil de Cliente Recurrente (Fidelización)
- [ ] Crear la tabla `clientes` en Supabase para almacenar el perfil de los usuarios.
- [ ] Implementar la función de guardar dirección y coordenadas GPS automáticamente al confirmar un pedido.
- [ ] Inyectar notas del sistema al chat de Gemini si detectamos que el cliente es recurrente para evitar pedirle dirección/nombre de nuevo.
- [ ] Programar la lógica de acumulación de puntos de fidelidad y canje de premios (ej: refresco o delivery gratis).

### ⏳ Fase C: Seguridad y Producción (Antes de Lanzar)
- [ ] Implementar sistema de lista negra (`bloqueados.json` o tabla) controlada por comando de administrador (`BLOQUEAR / DESBLOQUEAR [telefono]`).
- [ ] Configurar límite de ritmo (Rate Limiting) para evitar spam de usuarios maliciosos.
- [ ] Migrar el código a un servidor en la nube permanente (ej. Render o VPS) y configurar el número de WhatsApp comercial real.
