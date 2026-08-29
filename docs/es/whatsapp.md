# WhatsApp

> Read in English: [whatsapp.md](../en/whatsapp.md)

OpenLivery conecta un número real de WhatsApp a cada cliente para que su agente responda las conversaciones automáticamente. Cada cliente tiene su propia sesión, vinculada al escanear un código QR desde la app móvil de WhatsApp, sin necesidad de una cuenta de la WhatsApp Business API.

## El servicio puente

El soporte de WhatsApp corre en un servicio dedicado, el **puente** (`apps/whatsapp/`), un proceso de Node.js con estado construido sobre [Baileys](https://github.com/WhiskeySockets/Baileys), el protocolo de WhatsApp Web. El puente mantiene un socket activo por cada cliente conectado y se comunica con el backend a través de una API interna.

Como tiene estado, el puente no guarda las sesiones solo en memoria: el estado de sesión y autenticación se almacena cifrado a través del backend en PostgreSQL. Al arrancar, el puente pide al backend la lista de canales habilitados que ya tienen una sesión guardada y los recarga, de modo que los números se reconectan solos tras un reinicio.

## Conectar un número

Una sesión de WhatsApp pertenece a un solo cliente. Para conectarla:

1. Abre un **cliente**, ve a su canal de **WhatsApp** y elige el agente que responderá los mensajes entrantes.
2. Pulsa conectar. El backend le pide al puente iniciar una sesión y aparece un **código QR**.
3. En el teléfono dueño del número, abre WhatsApp y ve a **Ajustes → Dispositivos vinculados → Vincular un dispositivo**.
4. Escanea el código QR. Cuando el teléfono lo confirme, el canal cambia a **conectado** y muestra el número vinculado.

A partir de ahí la sesión sobrevive a los reinicios. Si el número se desvincula desde el teléfono (o la sesión se invalida), el puente borra el estado de autenticación guardado y el canal vuelve a desconectado. También puedes desconectar desde la misma página, lo que cierra la sesión del dispositivo y elimina la sesión guardada.

## Cómo fluyen los mensajes

Cuando un contacto escribe al número:

1. El puente recibe el mensaje y lo reenvía al backend en `POST /api/whatsapp/channels/{channel_id}/inbound`.
2. El backend registra el mensaje en la conversación del cliente, recupera el conocimiento del agente y genera una respuesta con el agente asignado.
3. La respuesta se envía de vuelta al contacto en WhatsApp a través del puente.

Las imágenes y las notas de voz también se reenvían; cuando el agente tiene habilitada la comprensión de imagen o audio, se describen o transcriben antes de llegar al modelo. Consulta [Base de conocimiento](knowledge-base.md).

El backend y el puente se autentican en cada llamada entre sí con un secreto compartido, `WHATSAPP_BRIDGE_TOKEN`. El script de instalación lo genera por ti; consulta [Configuración](configuration.md).

## Intervención humana

Cada conversación tiene un `mode`, que es `ai` (el valor por defecto) o `human`. Cuando cambias una conversación al modo human, la IA deja de responderla —el backend sigue registrando los mensajes entrantes, pero no genera ninguna respuesta automática— para que una persona pueda tomar el control y responder directamente desde la [bandeja de entrada](inbox.md) o el [portal del cliente](client-portal.md). Vuelve a `ai` para devolver la conversación al agente.

## Otros canales

WhatsApp es el único canal de mensajería en el núcleo open source por ahora. Instagram y Facebook Messenger están en la hoja de ruta.

Siguiente: gestiona las conversaciones en vivo en la [bandeja de entrada](inbox.md) o deja que los clientes gestionen las suyas en el [portal del cliente](client-portal.md).
