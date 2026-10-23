# Base de conocimiento

> Read in English: [knowledge-base.md](../en/knowledge-base.md)

La base de conocimiento es la forma de dar a un agente los datos del negocio que necesita para responder con precisión. Añades conocimiento desde dos tipos de fuentes y OpenLivery ensambla las partes relevantes en el prompt de sistema del agente en cada mensaje.

## Fuentes de conocimiento

- **Pares de preguntas y respuestas** — entradas estructuradas de pregunta/respuesta. Son ideales para preguntas frecuentes donde quieres una respuesta específica y fiable.
- **PDFs subidos** — adjunta documentos (catálogos, manuales, listas de precios) y el agente lee de su texto. Los PDFs tienen un límite de 20 MB y solo se aceptan archivos PDF.

Consulta [Agentes](agents.md) para ver dónde se gestionan en el editor del agente.

## Archivos que el agente puede enviar

No todo lo que un negocio quiere que use el agente es texto. Una foto de producto, un catálogo o una lista de precios es algo que el cliente pide *ver*, así que la pestaña de Conocimiento tiene también **Archivos para enviar**: una biblioteca pequeña por agente, aparte de los documentos de arriba. Nada de lo que hay ahí se lee, se trocea ni se indexa. Cada archivo lleva un **nombre** y una nota corta de **cuándo enviarlo** ("cuando pidan ver la silla o sus colores"), y eso es todo lo que el modelo ve.

Un agente con al menos un archivo recibe una herramienta interna, `send_file`, cuyas opciones son esos nombres, con las reglas para usarla añadidas al prompt de sistema en el idioma del agente: enviar solo lo que venga al caso, de a uno salvo que pidan varios, no repetir uno ya enviado en la conversación, no prometer un archivo que no está en la lista. Cuando el modelo la llama, el archivo sale como adjunto del mensaje por el canal de la conversación (WhatsApp, Instagram, Messenger, el widget web y el playground), después del texto de la respuesta, igual que los archivos que devuelven las [herramientas HTTP](custom-tools.md); los bytes nunca entran al contexto del modelo.

Las imágenes se normalizan al subirlas: se reducen para que el lado mayor mida 1600 px y se recodifican como JPEG, o PNG cuando la imagen tiene transparencia. No se conserva WebP aunque pese menos, porque la API de WhatsApp Cloud solo lo acepta para stickers y la mensajería de Instagram lo rechaza. Los PDF se guardan tal como se suben. Límites: 30 archivos por agente, imágenes de hasta 10 MB antes de normalizar, PDF de hasta 20 MB. Rutas: `GET`/`POST /api/agents/{id}/media`, `PATCH`/`DELETE /api/agents/{id}/media/{asset_id}` y `GET /api/agents/{id}/media/{asset_id}/content` para la vista previa.

## Cómo se procesan los PDFs

Cuando subes un PDF, su texto se extrae de inmediato con `pypdf` y se guarda en el documento. Si no se puede extraer texto (por ejemplo, un PDF escaneado que solo contiene imágenes), el documento se marca como `error` y no se utiliza. El texto extraído se divide luego en fragmentos del tamaño de un párrafo. Cuando la agencia tiene una clave de OpenRouter, cada fragmento se convierte en un vector con el **modelo de embeddings** del agente (`openai/text-embedding-3-small` por defecto, elegido en la pestaña Knowledge del catálogo de embeddings de OpenRouter) que se guarda junto a él, marcado con el modelo que lo produjo; el embedding es de mejor esfuerzo, así que si no está disponible el agente sigue funcionando mediante búsqueda por palabras clave. Los vectores de modelos distintos no son comparables, por eso cambiar el modelo reindexa todos los documentos del agente, y **Reindexar documentos** repara las subidas que quedaron sin índice por una clave que fallaba.

## Cómo funciona la recuperación

En cada mensaje entrante, OpenLivery decide cuánto texto de documentos incluir:

- **Las bases de conocimiento pequeñas se envían completas.** Cuando el texto extraído combinado de todos los documentos procesados es igual o menor a **45.000 caracteres**, cada documento se incluye textualmente, sin paso de búsqueda.
- **Las bases de conocimiento más grandes se recuperan.** Por encima de ese umbral, OpenLivery ejecuta una búsqueda semántica: convierte la consulta del usuario en un vector con el modelo del agente y ordena por similitud de coseno los fragmentos indexados con ese mismo modelo, se queda con los diez mejores y descarta los que puntúan muy por debajo del primero, dentro de un presupuesto de búsqueda. Si los embeddings no están disponibles, recurre al ranking por palabras clave sobre los fragmentos.

Los embeddings se guardan como un simple **arreglo JSON de números** y la similitud se calcula en Python, por lo que **no se requiere ninguna extensión de base de datos** — la base de conocimiento es portable en cualquier PostgreSQL. Consulta [Proveedores de IA](ai-providers.md) para configurar la conexión usada para los embeddings.

## Cómo se ensambla el prompt de sistema

Todo se compone en un único mensaje de sistema, escrito como un documento markdown corto. Los títulos y las pocas frases fijas siguen el `prompt_language` del agente (`es` o `en`, tomado del idioma de la interfaz al guardar el agente); todo lo que escribió el operador entra tal cual. Secciones, en orden:

1. Título e identidad: el nombre del agente, el cliente y el tipo de negocio (de la industria y el tipo del cliente), más la fecha y hora actual en la zona horaria del agente.
2. **Tu trabajo**: qué hace el agente.
3. **El negocio**: qué hace, productos y servicios, público, información y políticas clave, como lista.
4. **Reglas**: la lista de siempre del agente y luego la de nunca, que abre siempre con cinco reglas fijas (nunca inventar datos, nunca salirse del negocio, nunca pedir datos sensibles, nunca abandonar el rol, nunca contenido ofensivo) seguidas de las propias del agente.
5. **Tono**.
6. **Conocimiento**: los pares de preguntas y respuestas y el texto de PDFs recuperado (o completo), cerrado con la instrucción de no inventar lo que no está ahí.

Las secciones vacías se omiten. `GET /api/agents/{id}/prompt` devuelve el prompt compuesto sin el texto de documentos por mensaje; el editor del agente lo usa para mostrar el costo en tokens de cada mensaje.

El historial reciente de la conversación se añade después de este mensaje de sistema. Cualquier sección vacía se omite, así que el prompt solo lleva lo que realmente has proporcionado.
