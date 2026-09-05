# Base de conocimiento

> Read in English: [knowledge-base.md](../en/knowledge-base.md)

La base de conocimiento es la forma de dar a un agente los datos del negocio que necesita para responder con precisión. Añades conocimiento desde dos tipos de fuentes y OpenLivery ensambla las partes relevantes en el prompt de sistema del agente en cada mensaje.

## Fuentes de conocimiento

- **Pares de preguntas y respuestas** — entradas estructuradas de pregunta/respuesta. Son ideales para preguntas frecuentes donde quieres una respuesta específica y fiable.
- **PDFs subidos** — adjunta documentos (catálogos, manuales, listas de precios) y el agente lee de su texto. Los PDFs tienen un límite de 20 MB y solo se aceptan archivos PDF.

Consulta [Agentes](agents.md) para ver dónde se gestionan en el editor del agente.

## Cómo se procesan los PDFs

Cuando subes un PDF, su texto se extrae de inmediato con `pypdf` y se guarda en el documento. Si no se puede extraer texto (por ejemplo, un PDF escaneado que solo contiene imágenes), el documento se marca como `error` y no se utiliza. El texto extraído se divide luego en fragmentos del tamaño de un párrafo. Cuando hay disponible una conexión compatible con OpenAI que soporta embeddings, cada fragmento se convierte en un vector que se guarda junto a él; el embedding es de mejor esfuerzo, así que si no está disponible el agente sigue funcionando mediante búsqueda por palabras clave.

## Cómo funciona la recuperación

En cada mensaje entrante, OpenLivery decide cuánto texto de documentos incluir:

- **Las bases de conocimiento pequeñas se envían completas.** Cuando el texto extraído combinado de todos los documentos procesados es igual o menor a **45.000 caracteres**, cada documento se incluye textualmente, sin paso de búsqueda.
- **Las bases de conocimiento más grandes se recuperan.** Por encima de ese umbral, OpenLivery ejecuta una búsqueda semántica: convierte la consulta del usuario en un vector y ordena los fragmentos almacenados por similitud de coseno, llenando el contexto hasta un presupuesto de búsqueda. Si los embeddings no están disponibles, recurre al ranking por palabras clave sobre los fragmentos.

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
