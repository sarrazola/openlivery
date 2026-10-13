# Notificaciones push

> Read in English: [push-notifications.md](../en/push-notifications.md)

OpenLivery trae la *fontanería* de notificaciones y ningún *proveedor*. En una
instalación por defecto no hay cuenta que crear, ningún tercero involucrado y
nada que pagar: `PUSH_PROVIDER` vale `none` y el servidor no envía nada.

Esta página explica qué hace esa fontanería, qué opciones tienes para
encenderla, y la restricción que suele tomar a la gente por sorpresa.

## La restricción que conviene leer primero

En iOS y Android las credenciales de push están atadas al **binario de la app**,
no al servidor. Apple emite una clave APNs para la cuenta de desarrollador que
publica la app; Google emite un sender de FCM para el nombre del paquete. Un
servidor solo puede notificar a una app compilada contra el proveedor por el que
ese servidor envía.

La consecuencia práctica:

- **Corres tu propio OpenLivery y usas la app oficial de la tienda.** Esa app
  lee y responde todo en tu servidor sin problema, pero no puede recibir push
  desde él: la compilación de la tienda solo acepta notificaciones de las
  credenciales con las que se firmó, que son de quien la publicó. Es el modelo
  de Apple y de Google, no una limitación que añadimos nosotros.
- **Compilas la app tú mismo** con tu propio identificador de paquete y tus
  credenciales de push, que es justo lo que ya soporta la configuración de marca
  blanca; mira [`apps/mobile/WHITELABEL.md`](../../apps/mobile/WHITELABEL.md).
  Ahí el push es enteramente tuyo: eliges el proveedor, tienes las claves, y le
  pagas a quien elegiste (o a nadie).

Así que el push no es algo que le falte a un servidor autoalojado. Es algo que
viene con compilar tu propia app, y esta costura es lo que conecta las dos.

## Cómo funciona

Tres piezas, todas en el core:

1. **Un registro de dispositivos.** Cuando alguien inicia sesión en un teléfono,
   la app se registra con `POST /api/mobile/devices` y envía el token que le dio
   su proveedor. `GET /api/mobile/session` responde con `push.provider`, así que
   una app apuntada a un servidor con el push apagado no inicializa ningún SDK
   de push: nadie se suscribe, así que a nadie se le factura.
2. **Un punto de despacho.** Cuando llega un mensaje a una conversación que un
   operador tomó, el servidor notifica a los dispositivos registrados de ese
   cliente. Mientras responde el asistente no se envía nada: un teléfono que
   vibra con cada mensaje de cada cliente es un teléfono al que le apagan las
   notificaciones.
3. **Un proveedor.** Una sola función que recibe una `Notification` y la
   entrega.

## Encenderlo

### `none` (por defecto)

No envía nada. Sin configuración, sin dependencias, sin coste.

### `webhook`

Cada notificación se envía por POST como JSON a una URL que tú controlas, y
desde ahí la enrutas: ntfy, Gotify, Home Assistant, un incoming hook de Slack,
una cola, o un script de cinco líneas que llame al servicio que ya pagas.

```bash
PUSH_PROVIDER=webhook
PUSH_WEBHOOK_URL=https://example.com/openlivery-push
PUSH_WEBHOOK_SECRET=a-shared-secret   # optional; sent as a Bearer token
```

El cuerpo es estable:

```json
{
  "title": "Marta Ruiz",
  "body": "Hi, are you open on Saturday?",
  "data": { "conversation_id": "…", "client_id": "…" },
  "devices": [{ "token": "…", "platform": "ios" }]
}
```

### Tu propio proveedor

Un proveedor es una única función asíncrona. Regístrala al arrancar, desde un
módulo envoltorio que importe la app, y así nunca tienes que editar este
repositorio:

```python
from app.services.notifications import Notification, register_provider

async def send_via_my_service(notification: Notification) -> int:
    ...  # deliver however you like
    return len(notification.devices)

register_provider("my-service", send_via_my_service)
```

Después pon `PUSH_PROVIDER=my-service`. Registrar un nombre que ya existe lo
reemplaza, así que también puedes sustituir uno de los incluidos sin hacer un
fork.

Las filas de dispositivos recuerdan qué proveedor emitió su token, y los tokens
de un proveedor que ya no usas se saltan en vez de enviarse a un sitio donde no
pueden llegar. Después de cambiar de proveedor, las apps se vuelven a registrar
en su siguiente arranque.

## Navegadores: el portal, sin proveedor

Los teléfonos necesitan un proveedor porque sus credenciales push pertenecen a
quien compiló la app. Los navegadores no: el protocolo Web Push deja que
cualquier servidor entregue a cualquier navegador siempre que firme con un par
de claves propio (VAPID). Así el portal puede avisar con el portal cerrado y el
navegador abierto, en una instalación propia, sin cuenta en ningún sitio.

Se enciende generando el par de claves una vez y conservándolo:

```bash
python -m app.webpush_keys
# PUSH_WEBPUSH_PRIVATE_KEY=...
```

Pon la clave privada en `PUSH_WEBPUSH_PRIVATE_KEY` y, si quieres, a quién pueden
contactar los fabricantes de navegadores sobre este remitente en
`PUSH_WEBPUSH_SUBJECT` (`mailto:ops@ejemplo.com`). La mitad pública se deriva en
tiempo de ejecución y se entrega a la página. No rotes la clave a la ligera:
todo navegador suscrito con la anterior tiene que suscribirse de nuevo.

Desde entonces cada persona tiene un interruptor **Notificaciones del
navegador** en Ajustes, Preferencias, de su portal. Al encenderlo el navegador
pide permiso, la suscripción se registra para esa persona y el servidor entrega
directo al servicio push del navegador (`apps/api/app/services/webpush.py`,
RFC 8030, 8291 y 8292). Las suscripciones viven en el mismo registro de
dispositivos que los teléfonos, bajo el proveedor `webpush`, y llegan a las
mismas personas que ellos. Una suscripción que el servicio push declara
desaparecida (permiso revocado, navegador reiniciado) se descarta en el acto.
Mientras una ventana del portal está visible, la página muestra el mensaje en
su sitio en vez de levantar una notificación del sistema encima.

Web push es independiente de `PUSH_PROVIDER`: un despliegue puede avisar a los
teléfonos por un proveedor y a los navegadores directamente, o solo a los
navegadores.

## A quién se notifica

Las notificaciones van a todos los dispositivos registrados del **cliente** al
que pertenece la conversación. Si una barbería tiene tres personas atendiendo,
suenan los tres teléfonos y se la queda quien llegue primero. Los dispositivos
también están ligados al usuario del portal que los registró, así que quitar a
alguien de `/clients/{id}/portal-users` corta su teléfono de inmediato.

## Comportamiento ante fallos

La entrega es de mejor esfuerzo, a propósito. El mensaje ya está guardado y va a
estar ahí cuando la app se abra, así que un proveedor caído, mal configurado o
lento nunca hace fallar la petición que lo originó. Los fallos se registran en
el log y se tragan.
