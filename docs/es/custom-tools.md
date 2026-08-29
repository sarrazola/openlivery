# Herramientas personalizadas

> Read in English: [custom-tools.md](../en/custom-tools.md)

Las herramientas personalizadas permiten que un agente actúe, no solo responda. Desde la pestaña **Herramientas** del editor del agente puedes conectar dos tipos de herramientas, y el agente decide cuándo llamarlas durante una conversación: **herramientas HTTP** (un endpoint propio o cualquier API REST) y **servidores MCP** (servicios externos que hablan el Model Context Protocol). Las herramientas funcionan en todos los canales: el playground, el widget web y WhatsApp.

## Herramientas HTTP

Una herramienta HTTP describe un endpoint que el agente puede llamar:

- **Nombre** — en `snake_case`, se usa como el nombre de función que ve el modelo (por ejemplo `check_order`). No se permiten guiones bajos consecutivos.
- **URL y método** — la URL puede contener placeholders `{param}` (por ejemplo `https://api.example.com/orders/{order_id}`); cada placeholder se convierte automáticamente en una entrada obligatoria que el modelo debe proporcionar. Métodos: GET, POST, PUT, PATCH o DELETE.
- **Instrucciones para el prompt** — dile al agente cuándo y cómo usar la herramienta. Este texto se añade a la descripción que ve el modelo, así que sé específico con las condiciones y los datos requeridos.
- **Parámetros de body y query** — cada parámetro tiene nombre, tipo (`string`, `number`, `integer`, `boolean`), descripción y si es obligatorio. Los parámetros de body solo se permiten en POST, PUT y PATCH.
- **Opciones avanzadas** — headers de autenticación (por ejemplo `Authorization: Bearer …`) y un timeout entre 1 y 120 segundos (30 por defecto). Los valores de los headers se **guardan cifrados** y la API no los devuelve ni la UI los vuelve a mostrar; solo puedes reemplazarlos.

Cuando el modelo llama la herramienta, OpenLivery sustituye los placeholders de la ruta, envía los parámetros de query y el body JSON declarados, y devuelve la respuesta al modelo como `HTTP <status>: <body>`. Las respuestas se limitan a 100 KB.

## Servidores MCP

Un servidor MCP conecta al agente con todas las herramientas que ese servidor expone:

- **Nombre del servidor** — en `snake_case`, hasta 24 caracteres. Las herramientas del servidor se exponen al modelo como `<servidor>__<herramienta>` (por ejemplo `weather__get_forecast`), lo que evita colisiones de nombres entre servidores.
- **URL y transporte** — Streamable HTTP o SSE.
- **Headers de autenticación** — opcionales, cifrados igual que en las herramientas HTTP.

Antes de guardar un servidor debes ejecutar **Probar conexión**, que conecta, realiza el handshake MCP y lista las herramientas del servidor. La lista descubierta se guarda en caché y se reutiliza durante el chat, así las conversaciones nunca esperan por el descubrimiento; editar la URL, el transporte o los headers repite la comprobación. Crear o actualizar un servidor cuya conexión falla se rechaza.

## Cómo funciona el tool calling

Cuando un agente con herramientas activas recibe un mensaje, OpenLivery envía las definiciones de las herramientas al modelo junto con la conversación. Si el modelo decide llamar una herramienta, OpenLivery la ejecuta (la petición HTTP, o una llamada proxied al servidor MCP), le devuelve el resultado y deja que el modelo continúe — hasta **5 rondas** por respuesta, tras las cuales el modelo debe responder con texto. Funciona con ambos proveedores: OpenAI (Responses API) y Anthropic (Messages API). El uso de tokens de todas las rondas se suma en el registro de uso de la respuesta.

Cada respuesta del asistente guarda qué herramientas se ejecutaron, con sus argumentos y una vista previa de cada resultado. En el playground verás un chip bajo la respuesta con las herramientas usadas; las llamadas fallidas se resaltan y muestran el detalle del error, para diagnosticar una herramienta rota sin leer logs.

Si una llamada falla, el agente tiene instrucciones de decirle al usuario que la información o acción no está disponible en este momento — no responderá en silencio con su propio conocimiento.

## Seguridad

- **Las redes privadas están bloqueadas por defecto.** Las URLs de herramientas HTTP que resuelven a direcciones privadas, de loopback o reservadas (incluidos los endpoints de metadata de la nube) se rechazan en el momento de la petición. Los despliegues autoalojados que necesiten herramientas contra servicios internos pueden desactivarlo con `TOOLS_ALLOW_PRIVATE_URLS=true`.
- **Las redirecciones nunca se siguen.** Una respuesta 3xx cuenta como llamada fallida: el dato no se obtuvo, y seguir redirecciones a ciegas evadiría la comprobación de direcciones.
- **Los secretos permanecen cifrados.** Los headers de autenticación se cifran con la misma `ENCRYPTION_KEY` de las claves de proveedores (ver [Configuración](configuration.md)) y nunca vuelven al navegador.

## Solución de problemas

- **"Could not connect to the MCP server"** — el mensaje incluye la causa: credenciales rechazadas (revisa el formato del header `Authorization`, normalmente `Bearer <token>`), host inalcanzable, timeout, o un endpoint que no responde como servidor MCP (revisa la URL y el transporte).
- **El agente nunca llama la herramienta** — haz concretas las instrucciones del prompt ("Úsala cuando el cliente pregunte por el estado de un pedido"), verifica que el toggle de la herramienta esté activo, y menciona el dato en tu mensaje de prueba ("¿cuál es el estado del pedido 42?").
- **Una herramienta que funcionaba empieza a fallar** — la API destino puede haberse movido detrás de una redirección o cambiado la autenticación. El detalle del error en el playground muestra el status exacto que recibió la herramienta.

Consulta [Agentes](agents.md) para el resto del editor del agente y [Proveedores de IA](ai-providers.md) para conectar un modelo con soporte de tool calling.
