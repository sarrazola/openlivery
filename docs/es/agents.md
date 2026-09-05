# Agentes

> Read in English: [agents.md](../en/agents.md)

Un agente es el asistente de IA que conversa con tus usuarios finales. Cada agente pertenece a un único cliente, y cada agente lleva sus propias instrucciones, elección de modelo, conocimiento y ajustes multimodales. Esta página cubre cómo crear uno y qué hace cada ajuste.

## Qué es un agente

Un agente vive bajo un cliente (`Agency → Client → Agent`). El cliente es solo la identidad del negocio: su nombre, su industria y su tipo de negocio, elegidos de un catálogo fijo. Todo lo que el negocio hace y cómo debe responderse se escribe en el agente, así que dos agentes del mismo cliente pueden describirlo de forma distinta. Un agente define cómo debe comportarse, qué proveedor y modelo responden sus mensajes, cuánto historial de conversación recuerda y si puede entender imágenes y audio entrantes. Puedes crear tantos agentes por cliente como necesites — por ejemplo, uno para WhatsApp y otro incrustado como widget web.

## Crear un agente con el asistente

Los agentes nuevos se crean mediante un asistente de cinco pasos (**Agents → New agent**):

1. **Plantilla** — elige una plantilla inicial por industria o empieza en blanco. Las plantillas rellenan qué hace el agente y su tono para que tengas un prompt funcional desde el primer minuto.
2. **Identidad** — elige el cliente propietario y nombra el agente.
3. **Instrucciones** — escribe qué hace el agente y cómo debe sonar. Un contador de tokens en vivo estima el tamaño del prompt mientras escribes.
4. **Modelo** — define la zona horaria, el proveedor y el modelo, y ajusta la temperatura, los tokens máximos y la memoria. Una barra de ventana de contexto muestra cuánto de la ventana del modelo usa el prompt.
5. **Revisión** — confirma el resumen y crea el agente.

Las plantillas iniciales incluidas son Pedidos de restaurante, Leads inmobiliarios, Citas de clínica, Soporte de tienda online y Atención al cliente. Después de crearlo refinas todo en la página de detalle del agente, donde **Básicos** reúne cliente, nombre, brief del negocio, trabajo del agente, escalamiento y modelo. La sección del modelo muestra cuántos tokens cuesta el prompt compuesto en cada mensaje. Crear un cliente termina en el asistente con ese cliente preseleccionado.

## Elegir proveedor y modelo

Cada agente usa un proveedor — `openai` o `anthropic` — y un modelo de ese proveedor. Se utiliza la clave API almacenada de la agencia para ese proveedor, así que añade tus claves primero. Consulta [Proveedores de IA](ai-providers.md) para ver los modelos disponibles y cómo se configuran las claves. El campo de modelo acepta un valor personalizado si usas un modelo que no está en la lista de presets.

## Capacidades multimodales

Un agente entiende los medios entrantes desde el inicio: ambas capacidades vienen activas en los agentes nuevos. Cada una tiene su propio interruptor y su propio ajuste de modelo, independiente del modelo de chat principal, dentro de las opciones avanzadas de la sección del modelo:

- **Reconocimiento de imágenes (visión)** — cuando `image_enabled` está activo, las imágenes entrantes se describen con el modelo de `image_model` antes de llegar al agente.
- **Transcripción de audio** — cuando `audio_enabled` está activo, el audio entrante se transcribe con el modelo de `audio_model` (por defecto `whisper-1`) antes de llegar al agente.

Ambas funciones usan modelos de OpenAI, por lo que requieren una clave de OpenAI sin importar el proveedor de chat del agente.

## Ajustes del agente

| Ajuste | Campo | Qué hace |
| --- | --- | --- |
| Cliente | `client_id` | El cliente propietario del agente. |
| Qué hace el agente | `instructions` | Su trabajo, tareas y reglas, en prosa. Va dentro del prompt del sistema. |
| Tono | `personality` | Guía de tono y estilo para las respuestas. |
| Brief del negocio | `brief_summary`, `brief_products`, `brief_audience`, `brief_policies`, `brief_dos`, `brief_donts` | Qué es y qué ofrece el negocio, más las reglas de siempre/nunca del agente. Se compone en el prompt del sistema. |
| Identidad del negocio | `industry`, `business_type`, `business_custom` (en el cliente) | Códigos del catálogo (`GET /api/industries`) que nombran el tipo de negocio en la primera línea del prompt; cuando el catálogo solo ofrece "otro", `business_custom` guarda las palabras del propio cliente. |
| Idioma del prompt | `prompt_language` | `es` o `en`: el idioma de los títulos y frases fijas del prompt. Se toma del idioma de la interfaz al guardar el agente. |
| Zona horaria | `timezone` | Zona horaria IANA (p. ej. `America/Bogota`) inyectada para que el agente conozca la fecha y hora locales. Por defecto `UTC`. |
| Proveedor | `provider` | `openai` o `anthropic`. |
| Modelo | `model` | El modelo de chat usado para las respuestas. |
| Temperatura | `temperature` | Aleatoriedad del muestreo, `0.0`–`2.0` (por defecto `0.7`). |
| Tokens máximos | `max_tokens` | Máximo de tokens por respuesta, `1`–`32000` (por defecto `2048`). |
| Límite de memoria | `memory_limit` | Cuántos mensajes pasados se conservan como memoria de conversación, `0`–`200` (por defecto `30`). |
| Reconocimiento de imágenes | `image_enabled`, `image_model` | Activa la visión y elige el modelo que describe las imágenes entrantes. |
| Transcripción de audio | `audio_enabled`, `audio_model` | Activa la transcripción y elige el modelo que transcribe el audio entrante (por defecto `whisper-1`). |

Los parámetros de muestreo se aplican con mejor esfuerzo; los modelos que rechazan un valor recurren a sus propios valores por defecto.

## El conocimiento en el prompt del sistema

Más allá de estos ajustes, los pares de preguntas y respuestas del agente, los documentos subidos, el contexto por cliente y el contexto por agente se ensamblan en el prompt del sistema al momento de responder. Consulta [Base de conocimiento](knowledge-base.md) para ver cómo se fragmentan, se generan embeddings y se recuperan los documentos.
