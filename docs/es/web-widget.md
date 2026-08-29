# Widget de chat web

> Read in English: [web-widget.md](../en/web-widget.md)

El widget web es un chat embebible, respaldado por uno de tus agentes, que puedes colocar en cualquier sitio web con una sola etiqueta `<script>`. Los visitantes ven un botón de chat flotante; al abrirlo hablan con el agente a través de la API pública de OpenLivery, con el mismo conocimiento e instrucciones que configuraste.

## Cómo funciona

Cada agente tiene un `widget_public_id`: un identificador público que se usa en la ruta del widget `/widget/<publicId>`. El script de carga monta un `iframe` que apunta a esa ruta y añade un botón lanzador flotante. Como el id es público, el widget se sirve sin autenticación, así que nunca se expone al navegador nada sensible (claves de API, datos de otros clientes).

El widget solo funciona mientras está habilitado: el backend sirve los endpoints de configuración, historial y mensajes únicamente para agentes en los que `widget_enabled` está activo. Publica y habilita el agente antes de embeberlo.

## Habilitar y obtener el fragmento

1. Abre el agente y ve a la pestaña **Widget**.
2. Activa **Habilitar widget** y define el saludo, el color y la posición (izquierda o derecha).
3. Guarda y copia el fragmento de inserción desde la sección **Embed**. Un enlace de **Vista previa** abre el widget de forma independiente.

El fragmento apunta `data-agent` al id público del agente y pasa las opciones de apariencia como atributos de datos:

```html
<script
  src="https://your-openlivery-domain/widget.js"
  data-agent="AGENT_PUBLIC_ID"
  data-color="#075985"
  data-position="right"
  async
></script>
```

Pégalo antes de la etiqueta de cierre `</body>` de cualquier página. El origen de `src` debe ser tu despliegue de OpenLivery; `widget.js` deriva la URL del iframe de su propio origen.

## Mensajes y límite de peticiones

Cuando un visitante envía un mensaje, el widget llama al endpoint público `POST /api/widget/<publicId>/messages` con un `session_id` por navegador. El backend localiza el agente, añade el mensaje a una conversación `widget`, recupera el conocimiento, llama al proveedor configurado y devuelve la respuesta. El historial de la sesión se guarda en el `localStorage` del visitante, de modo que la conversación sobrevive a las recargas de página.

Estos endpoints públicos tienen límite de peticiones por IP de cliente (30 peticiones de mensaje por minuto) porque cada llamada consume tokens del LLM. Quien supere el límite recibe `429 Too Many Requests` con una cabecera `Retry-After`. El limitador lee la IP del cliente desde `X-Forwarded-For` que establece el gateway. Consulta [Configuración](configuration.md) para el interruptor `RATE_LIMIT_ENABLED`.

## Conversaciones del widget en el inbox

Cada chat del widget se convierte en una conversación del canal `widget`, así que aparece en el [Inbox](inbox.md) junto a los hilos de WhatsApp y del playground. Puedes filtrar por el canal del widget, leer la transcripción completa y cambiar una conversación a modo **humano**, lo que pausa la IA para que un operador responda directamente desde el portal.
