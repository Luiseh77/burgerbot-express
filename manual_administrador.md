# 📘 Manual de Administrador - BurgerBot Express Bot

Este manual contiene las instrucciones y comandos secretos para gestionar el bot de WhatsApp (repartidores, tasa de cambio y configuraciones) directamente desde tu teléfono celular.

---

## ⚠️ Requisito Importante: Teléfono Administrador
Por motivos de seguridad, el bot **solo obedecerá estos comandos** si se envían desde el número de teléfono configurado como `ADMIN_PHONE` en tu archivo `.env`. Si otra persona intenta enviar estos comandos, el bot los tratará como un mensaje normal de cliente.

---

## 🛵 1. Gestión de Repartidores (Libreta de Deliverys)
El bot cuenta con una libreta para registrar a los repartidores disponibles. Cuando un pedido se aprueba, el bot le enviará una notificación con el botón *"¡Yo lo llevo!"* a todos los repartidores registrados.

### A. Ver la lista de repartidores registrados
Envía este comando exacto al chat del bot:
```text
VER REPARTIDORES
```
* **Respuesta del bot:** Te enviará la lista completa de nombres y números telefónicos registrados actualmente.

### B. Agregar un nuevo repartidor
Envía el comando con el número de teléfono (con código de país, sin el símbolo `+`) y el nombre:
```text
AGREGAR REPARTIDOR [Teléfono] [Nombre Completo]
```
* **Ejemplo:**
  ```text
  AGREGAR REPARTIDOR 584140000001 RepartidorDemo
  ```
* **Respuesta del bot:** `✅ Repartidor RepartidorDemo (584140000001) agregado a la libreta exitosamente.`

### C. Eliminar un repartidor
Envía el comando seguido del número de teléfono del repartidor que deseas borrar:
```text
ELIMINAR REPARTIDOR [Teléfono]
```
* **Ejemplo:**
  ```text
  ELIMINAR REPARTIDOR 584140000001
  ```
* **Respuesta del bot:** `🗑️ Repartidor RepartidorDemo eliminado de la libreta.`

---

## 💵 2. Gestión de la Tasa de Cambio (Dólares a Bolívares)
Por defecto, el bot consulta de forma automática la tasa oficial del **BCV (Banco Central de Venezuela)** por internet. Sin embargo, puedes fijar una tasa manual en caso de emergencias o si deseas usar otra tasa.

### A. Fijar una tasa de cambio manual
Envía el comando con la tasa que deseas aplicar (utiliza un punto o coma para los decimales):
```text
FIJAR TASA [Monto]
```
* **Ejemplo:**
  ```text
  FIJAR TASA 38.50
  ```
* **Respuesta del bot:** `✅ Tasa manual fijada en 38.50 Bs. El bot ya no usará la tasa de internet.`

### B. Borrar la tasa manual (Volver a Tasa Automática)
Envía este comando para eliminar la tasa manual y que el bot vuelva a consultar la tasa oficial de internet automáticamente:
```text
BORRAR TASA
```
* **Respuesta del bot:** `✅ Tasa manual borrada. El bot vuelve a usar la tasa automática del BCV por internet.`

---

## 💳 3. Gestión de Métodos de Pago
Puedes agregar, desactivar, activar o eliminar los métodos de pago (Pago Móvil, Zelle, Paypal, Efectivo, etc.) directamente desde tu celular. La IA leerá automáticamente estos métodos y se los ofrecerá a los clientes al final de la compra.

### A. Ver todos los métodos de pago registrados
Envía este comando:
```text
VER PAGOS
```
* **Respuesta del bot:** Te mostrará una lista con los IDs, nombres, estado (Activo/Inactivo) y detalles de cada método registrado.

### B. Agregar o actualizar un método de pago
Envía el comando indicando un `id` único (una sola palabra, en minúsculas), el nombre público y el detalle del cobro separado por una barra vertical `|`:
```text
AGREGAR PAGO [id] [Nombre Público] | [Detalles del Pago]
```
* **Ejemplo de Pago Móvil:**
  ```text
  AGREGAR PAGO pago_movil Pago Móvil | Banco: 0102, CI: 12345678, Tlf: 04140000000
  ```
  *(Nota: Si usas el ID `pago_movil` y escribes Banco, CI y Tlf en los detalles, el bot extraerá automáticamente estos campos para generar el mensaje copiable rápido para los bancos en Venezuela).*
* **Ejemplo de Zelle:**
  ```text
  AGREGAR PAGO zelle Zelle | Correo: pagos@burgerbot.fake, Titular: BurgerBot Express LLC
  ```
* **Ejemplo de Paypal:**
  ```text
  AGREGAR PAGO paypal PayPal | Enlace: paypal.me/burgerbotexpress (Comisión a cargo del cliente)
  ```

### C. Activar o desactivar temporalmente un método
Si una de tus cuentas está en mantenimiento, puedes desactivar el método temporalmente para que la IA no se lo mencione a los clientes:
```text
DESACTIVAR PAGO [id]
ACTIVAR PAGO [id]
```
* **Ejemplos:**
  * `DESACTIVAR PAGO zelle` (desactiva Zelle).
  * `ACTIVAR PAGO zelle` (lo vuelve a activar).

### D. Eliminar definitivamente un método de pago
Envía el comando con el ID correspondiente:
```text
ELIMINAR PAGO [id]
```
* **Ejemplo:** `ELIMINAR PAGO paypal`

---

## 📋 4. Archivos de Configuración en el Proyecto
Si prefieres editar la configuración desde la computadora, estos son los archivos clave en tu proyecto:

1. 📂 **`repartidores.json`:** Almacena la lista de repartidores registrados.
2. 📂 **`tasa.json`:** Se genera automáticamente al fijar la tasa manual. Si lo borras, se borra la tasa manual.
3. 📂 **`metodos_pago.json`:** Almacena los métodos de pago, detalles y estados de activación.
4. 📂 **`tarifas_delivery.json`:** Define los precios del delivery por zona (Centro, Norte, Sur). El bot los leerá de forma dinámica.
