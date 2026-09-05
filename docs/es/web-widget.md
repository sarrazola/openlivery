# Widget de chat web

> Read in English: [web-widget.md](../en/web-widget.md)

El widget web es un chat embebible, un canal de un cliente atendido por uno de sus agentes, que puedes colocar en cualquier sitio web con una sola etiqueta `<script>`. Los visitantes ven un botón de chat flotante; al abrirlo hablan con el agente a través de la API pública de OpenLivery, con el mismo conocimiento e instrucciones que configuraste.

## Cómo funciona

El chat web es un canal del cliente, como sus líneas de WhatsApp: cada cliente tiene como máximo uno, y tú eliges cuál de sus agentes lo atiende. El canal lleva un id público que se usa en la ruta del widget `/widget/<publicId>`. El script de carga monta un `iframe` que apunta a esa ruta y añade un botón lanzador flotante.

El widget solo funciona mientras el canal está activado y el cliente está activo: el backend sirve los endpoints de configuración, historial y mensajes únicamente entonces. El id público es del canal, no del agente, así que puedes cambiar o reemplazar el agente sin tocar los sitios donde está insertado el fragmento.

## Configurarlo y obtener el fragmento

1. Abre el cliente, ve a **Canales** y elige **Chat web** (o usa la página de Canales y elige el cliente).
2. Elige el agente que responde, define el saludo, el color y la posición (izquierda o derecha), y deja activado **Activar chat web**.
3. Guarda y copia el fragmento de inserción desde la sección **Código de inserción**. Un enlace de **Previsualizar** abre el widget de forma independiente.

El fragmento apunta `data-agent` al id público del canal y pasa las opciones de apariencia como atributos de datos:

```html
<script
  src="https://your-openlivery-domain/widget.js"
  data-agent="CHANNEL_PUBLIC_ID"
  data-color="#075985"
  data-position="right"
  async
></script>
```

Pégalo antes de la etiqueta de cierre `</body>` de cualquier página. El origen del `src` debe ser tu despliegue de OpenLivery; `widget.js` deriva la URL del iframe de su propio origen.

## Mensajes y límite de peticiones

Cuando un visitante envía un mensaje, el widget llama al endpoint público `POST /api/widget/<publicId>/messages` con un `session_id` por navegador. El backend localiza el agente, añade el mensaje a una conversación `widget`, recupera el conocimiento, llama al proveedor configurado y devuelve la respuesta. El historial de la sesión se guarda en el `localStorage` del visitante, de modo que la conversación sobrevive a las recargas de página.

Estos endpoints públicos tienen límite de peticiones por IP de cliente (30 peticiones de mensaje por minuto) porque cada llamada consume tokens del LLM. Quien supere el límite recibe `429 Too Many Requests` con una cabecera `Retry-After`. El limitador lee la IP del cliente desde `X-Forwarded-For` que establece el gateway. Consulta [Configuración](configuration.md) para el interruptor `RATE_LIMIT_ENABLED`.

Mientras está abierto, el widget también consulta `GET /api/widget/<publicId>/updates` cada pocos segundos (con su propio límite, más amplio, de 120 por minuto), así que las respuestas que escribe una persona que tomó el control aparecen en vivo, con su nombre. Resolver una conversación cierra el caso: el siguiente mensaje del visitante abre uno nuevo, y el widget muestra el caso nuevo por separado; los chats anteriores quedan a un toque tras el botón de historial, solo lectura. Van ligados al id de sesión anónimo del navegador y viven en el servidor, así que recargar los conserva y solo borrar los datos del sitio los pierde.

## Conversaciones del widget en el inbox

Cada chat del widget se convierte en una conversación del canal `widget`, así que aparece en el [Inbox](inbox.md) junto a los hilos de WhatsApp y del playground. Puedes filtrar por el canal del widget, leer la transcripción completa y cambiar una conversación a modo **humano**, lo que pausa la IA para que un operador responda directamente desde el portal.
