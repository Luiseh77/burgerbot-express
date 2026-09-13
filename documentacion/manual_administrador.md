# Manual de Operaciones para el Administrador

Este manual contiene las instrucciones detalladas de los comandos de WhatsApp que tú (como administrador) puedes enviarle al bot para configurar el sistema al vuelo, gestionar repartidores, fijar tasas de cambio, administrar métodos de pago y gestionar roles del equipo.

---

## 👑 Jerarquía de Administradores (Exclusivo Súper Admin)

El número registrado en la variable `ADMIN_PHONE` del archivo `.env` es el **Súper Administrador** del sistema. Solo este número principal tiene permisos para gestionar a otros administradores.

Los **Administradores Secundarios** pueden utilizar todos los comandos comunes (gestionar repartidores, tasas y pagos, así como recibir y validar capturas de pago), pero no pueden agregar o eliminar a otros administradores.

### Comandos Exclusivos del Súper Administrador:

#### 1. Agregar un Administrador Secundario
Para otorgarle permisos de administrador a otro miembro del equipo:
```text
AGREGAR ADMINISTRADOR [telefono] [nombre]
```
* **Ejemplo:** `AGREGAR ADMINISTRADOR 584241112222 Carlos`
* *Nota:* El teléfono debe ingresarse sin el signo `+` y con el código de país.

#### 2. Eliminar un Administrador Secundario
Para quitarle los privilegios de administrador a un número:
```text
ELIMINAR ADMINISTRADOR [telefono]
```
* **Ejemplo:** `ELIMINAR ADMINISTRADOR 584241112222`

#### 3. Listar Administradores Secundarios
Para ver quiénes tienen permisos administrativos secundarios en el sistema:
```text
VER ADMINISTRADORES
```

---

## 🛵 Gestión de Repartidores (Libreta de Repartidores)

Cualquier administrador (Súper Admin o Secundario) puede gestionar la libreta de repartidores para definir a quiénes les llegarán los broadcasts de nuevos pedidos.

> [!IMPORTANT]
> **Regla de Comunicación Obligatoria (Restricción de 24 horas de WhatsApp):**
> Debido a las políticas oficiales de WhatsApp, el bot no puede enviar mensajes a un repartidor si este no le ha escrito primero al bot dentro de las últimas 24 horas.
> **Instrucción para tus repartidores:** Cada mañana, al iniciar su turno, cada repartidor debe enviar un mensaje de saludo al bot (por ejemplo, "Hola" o "Activo") para abrir la ventana de comunicación y recibir los pedidos del día.

### Comandos para Repartidores:

#### 1. Agregar un nuevo repartidor
```text
AGREGAR REPARTIDOR [telefono] [nombre]
```
* **Ejemplo:** `AGREGAR REPARTIDOR 584128484463 Ester`

#### 2. Eliminar un repartidor
```text
ELIMINAR REPARTIDOR [telefono]
```
* **Ejemplo:** `ELIMINAR REPARTIDOR 584128484463`

#### 3. Ver repartidores registrados
```text
VER REPARTIDORES
```

---

## 💵 Configuración de la Tasa de Cambio (Dólar a Bolívares)

Cualquier administrador puede fijar o borrar la tasa de cambio de emergencia.

### Comandos de Tasa:

#### 1. Fijar tasa de cambio manual (Emergencia)
```text
FIJAR TASA [monto]
```
* **Ejemplo:** `FIJAR TASA 38.50`

#### 2. Volver a tasa automática (Consultar BCV por internet)
```text
BORRAR TASA
```

---

## 💳 Gestión de Métodos de Pago

Cualquier administrador puede modificar los métodos de pago que se muestran a los clientes.

### Comandos de Métodos de Pago:

#### 1. Ver métodos de pago registrados
```text
VER PAGOS
```

#### 2. Agregar o actualizar un método de pago
```text
AGREGAR PAGO [id] [Nombre] | [Detalles]
```
* **Ejemplo Zelle:** `AGREGAR PAGO zelle Zelle | Correo: pagos@midelivery.com, A nombre de: BurgerBot Express LLC`
* **Ejemplo Pago Móvil (Mantiene formato para auto-copiable):**
  ```text
  AGREGAR PAGO pago_movil Pago Móvil | Banco: 0102, CI: 12345678, Tlf: 04140000000
  ```

#### 3. Desactivar temporalmente un método
```text
DESACTIVAR PAGO [id]
```
* **Ejemplo:** `DESACTIVAR PAGO zelle`

#### 4. Activar un método desactivado
```text
ACTIVAR PAGO [id]
```
* **Ejemplo:** `ACTIVAR PAGO zelle`

#### 5. Eliminar un método de pago
```text
ELIMINAR PAGO [id]
```
* **Ejemplo:** `ELIMINAR PAGO zelle`
