# Agentes

> Read in English: [agents.md](../en/agents.md)

Un agente es el asistente de IA que conversa con tus usuarios finales. Cada agente pertenece a un único cliente, y cada agente lleva sus propias instrucciones, elección de modelo, conocimiento y ajustes multimodales. Esta página cubre cómo crear uno y qué hace cada ajuste.

## Qué es un agente

Un agente vive bajo un cliente (`Agency → Client → Agent`). El cliente es solo la identidad del negocio: su nombre, su industria y su tipo de negocio, elegidos de un catálogo fijo. Todo lo que el negocio hace y cómo debe responderse se escribe en el agente, así que dos agentes del mismo cliente pueden describirlo de forma distinta. Un agente define cómo debe comportarse, qué proveedor y modelo responden sus mensajes, cuánto historial de conversación recuerda y si puede entender imágenes y audio entrantes. Puedes crear tantos agentes por cliente como necesites — por ejemplo, uno para WhatsApp y otro incrustado como widget web.

## Crear un agente con el asistente

Los agentes nuevos se crean mediante un asistente de cinco pasos (**Agents → New agent**); la cabecera de pasos es clicable para moverse entre los pasos ya alcanzados:

1. **Plantilla** — empieza desde cero (recomendado y preseleccionado) o elige una plantilla inicial por industria. Las plantillas rellenan qué hace el agente, su tono y el brief del negocio (qué hace, productos, público, información clave, siempre y nunca) en tu idioma, para que reemplaces los detalles con los del cliente.
2. **Identidad** — elige el cliente propietario y nombra el agente.
3. **Esenciales** — las tres cosas que el agente necesita para responder bien: qué hace el negocio, su información clave y políticas, y qué hace el agente. Productos, público, reglas de siempre/nunca y tono se completan después en Básicos del agente.
4. **Modelo** — proveedor y modelo, con el recomendado preseleccionado y cada opción etiquetada (recomendado, equilibrado, más potente), más, en opciones avanzadas, los ajustes de generación y las capacidades de imagen y audio.
5. **Revisión** — un resumen del agente y el tamaño de su prompt, y el botón de crear. Al crear se llega a Básicos del agente.

Las plantillas iniciales incluidas son Pedidos de restaurante, Leads inmobiliarios, Citas de clínica, Soporte de tienda online y Atención al cliente. Después de crearlo refinas todo en la página de detalle del agente, donde **Básicos** reúne cliente, nombre, brief del negocio, trabajo del agente, escalamiento y modelo. La sección del modelo muestra cuántos tokens cuesta el prompt compuesto en cada mensaje. Crear un cliente termina en el asistente con ese cliente preseleccionado.

## Elegir modelo

Cada agente elige un modelo por su slug de OpenRouter (`openai/gpt-6-luna`, `anthropic/claude-sonnet-5`, `google/gemini-3.8-flash`). Se utiliza la clave de OpenRouter almacenada de la agencia, así que añádela primero. Consulta [Proveedores de IA](ai-providers.md) para ver los modelos disponibles y cómo se configura la clave. El campo de modelo acepta cualquier slug escrito a mano si el modelo que quieres no está en la lista de presets.

## Capacidades multimodales

Un agente entiende los medios entrantes desde el inicio: ambas capacidades vienen activas en los agentes nuevos. Cada una tiene su propio interruptor y su propio ajuste de modelo, independiente del modelo de chat principal, dentro de las opciones avanzadas de la sección del modelo:

- **Reconocimiento de imágenes (visión)** — cuando `image_enabled` está activo, las imágenes entrantes se describen con el modelo de `image_model` antes de llegar al agente.
- **Transcripción de audio** — cuando `audio_enabled` está activo, el audio entrante se transcribe con el modelo de `audio_model` (por defecto `openai/gpt-4o-mini-transcribe`) antes de llegar al agente.

Ambas funciones pasan por la misma clave de OpenRouter que el modelo de chat.

## Ajustes del agente

| Ajuste | Campo | Qué hace |
| --- | --- | --- |
| Cliente | `client_id` | El cliente propietario del agente. |
| Tareas del agente | `instructions` | Su trabajo, tareas y reglas, en prosa. Va dentro del prompt del sistema. |
| Tono de comunicación | `personality` | Guía de tono y estilo para las respuestas. |
| Brief del negocio | `brief_summary`, `brief_products`, `brief_audience`, `brief_policies`, `brief_dos`, `brief_donts` | Qué es y qué ofrece el negocio, más las reglas de siempre/nunca del agente. Se compone en el prompt del sistema. |
| Identidad del negocio | `industry`, `business_type`, `business_custom` (en el cliente) | Códigos del catálogo (`GET /api/industries`) que nombran el tipo de negocio en la primera línea del prompt; cuando el catálogo solo ofrece "otro", `business_custom` guarda las palabras del propio cliente. |
| Contacto | de la conversación | Nombre, teléfono, correo, campos personalizados, etiquetas y canal de quien escribe, añadidos al prompt al responder para que un registro, un correo o una herramienta los reciba en vez de "no especificado". Solo se lista lo que la ficha del contacto tiene. No aparece en el playground. |
| Datos del contacto por recopilar | `capture_enabled`, `GET`/`PUT /api/agents/{id}/capture` | Lo que el agente le pregunta al cliente y guarda en el contacto. Ver [Recopilar datos del contacto](#recopilar-datos-del-contacto). |
| Seguimiento y cierre | `GET`/`PUT /api/agents/{id}/follow-ups` | Recordatorios y un mensaje de cierre cuando el cliente deja de responder, y si el agente puede resolver una conversación por sí mismo. Ver [Seguimiento y cierre](#seguimiento-y-cierre). |
| Idioma del prompt | `prompt_language` | `es` o `en`: el idioma de los títulos y frases fijas del prompt. Se toma del idioma de la interfaz al guardar el agente. |
| Zona horaria | `timezone` (en el cliente) | Zona horaria IANA del negocio (p. ej. `America/Bogota`), inyectada para que todos los agentes del cliente conozcan la fecha y hora locales. Se define en el cliente, por defecto `UTC`. |
| Proveedor | `provider` | Siempre `openrouter`. |
| Modelo | `model` | El modelo de chat usado para las respuestas, como slug de OpenRouter. |
| Temperatura | `temperature` | Aleatoriedad del muestreo, `0.0`–`2.0` (por defecto `0.7`). |
| Tokens máximos | `max_tokens` | Máximo de tokens por respuesta, `1`–`32000` (por defecto `2048`). |
| Límite de memoria | `memory_limit` | Cuántos mensajes pasados se conservan como memoria de conversación, `0`–`200` (por defecto `30`). |
| Espera antes de responder | `reply_delay_min_seconds`, `reply_delay_max_seconds` | Ventana de silencio antes de que el agente responda un mensaje de WhatsApp, elegida al azar entre los dos límites, `0`–`60` segundos cada uno (por defecto `6` a `9`). La ventana se reinicia con cada mensaje nuevo del visitante, así una ráfaga recibe una sola respuesta. Ambos en `0` responden cada mensaje de inmediato. El máximo debe ser mayor o igual que el mínimo. |
| Reconocimiento de imágenes | `image_enabled`, `image_model` | Activa la visión y elige el modelo que describe las imágenes entrantes. |
| Transcripción de audio | `audio_enabled`, `audio_model` | Activa la transcripción y elige el modelo que transcribe el audio entrante (por defecto `whisper-1`). |

Los parámetros de muestreo se aplican con mejor esfuerzo; los modelos que rechazan un valor recurren a sus propios valores por defecto.

## Recopilar datos del contacto

Un agente puede preguntarle datos al cliente y guardarlos en el contacto, así la
siguiente conversación con esa persona ya los tiene y el agente no vuelve a
preguntar. En **Datos del contacto**, dentro de los ajustes del agente, actívalo
y elige los campos: el nombre, correo y teléfono integrados, o cualquier campo
personalizado que el cliente haya definido, y si quieres los canales en los que
aplica cada uno (WhatsApp, Instagram, Messenger, chat web); sin ninguno elegido
aplica en todos. Qué es un campo y cuándo pedirlo es la descripción del propio
campo, así todos los agentes del cliente lo piden igual; los tres integrados
traen la suya.

Los campos personalizados pertenecen al cliente y los comparten todos sus agentes
y el portal del cliente: **Campos del contacto** en la página del cliente
(`/api/clients/{id}/contact-fields`). Un campo tiene una clave en `snake_case`
que usan el agente y el API (no se puede cambiar después), una etiqueta que ve la
gente, un tipo (texto, número, correo, teléfono) contra el que se valida el
valor, y una descripción que le dice al agente qué es el valor y cuándo pedirlo.
Eliminar un campo lo quita de todos los agentes y borra su valor de todos los
contactos que lo tenían.

Al responder, solo los campos que aún no se conocen de ese contacto llegan al
prompt, como una sección "Datos por capturar" con sus descripciones, y el agente
recibe la herramienta `save_contact_field`. La regla que sigue: preguntar con
naturalidad, de uno en uno, nunca como formulario, y guardar solo lo que el
cliente dijo explícitamente. Los valores integrados van a las columnas propias
del contacto; los personalizados a `attributes` en el contacto, que el portal
muestra y edita en la ficha (`PATCH /api/portal/{slug}/contacts/{id}` con
`attributes`). Un teléfono que ya tiene otro contacto no se sobrescribe. El
playground ensaya los campos sin guardar nada.

## Seguimiento y cierre

Sin estos ajustes, una conversación atendida por la IA termina de una sola
forma: 24 horas sin mensajes. **Seguimiento y cierre**, en los ajustes del
agente, agrega dos más.

**Seguimiento por inactividad.** Cuando el cliente deja de responder, el agente
retoma el contacto. Las reglas se agregan una por una: hasta dos recordatorios
y un mensaje de cierre, cada uno después de un número de horas contado desde el
último mensaje del agente. El mensaje de cierre resuelve la conversación, y el
siguiente mensaje del cliente abre una nueva. La secuencia también puede tener
solo recordatorios, y entonces la conversación queda para el cierre por
inactividad descrito abajo, o solo el mensaje de cierre.

Cada mensaje lo redacta la IA según la conversación, en el idioma del cliente,
o es un mensaje personalizado que se envía exactamente como está escrito, sin
llamar al modelo. Toda la secuencia cabe en 23 horas, porque WhatsApp Cloud
API, Instagram y Messenger solo aceptan mensajes libres durante las 24 horas
siguientes al último mensaje del cliente. Un mensaje que ya no se puede entregar
se omite, y un mensaje de cierre que no se puede entregar cierra el caso de
todos modos. Elige los canales donde aplican las reglas, o deja todos sin marcar
para que apliquen en todos. Las conversaciones del playground nunca reciben
seguimientos.

La secuencia se detiene en cuanto el cliente escribe, una persona toma la
conversación, se asigna o se escala, el negocio responde desde el teléfono o la
conversación se resuelve. La siguiente respuesta del agente la reinicia desde
la primera regla.

**Permitir que el agente resuelva la conversación.** Con esta opción, el agente
recibe la herramienta `resolve_conversation` y cierra el caso por sí mismo
cuando la solicitud quedó atendida y no hay nada pendiente. Primero se despide,
y la conversación se resuelve dos minutos después, salvo que el cliente vuelva
a escribir: en ese caso simplemente continúa. Si la misma respuesta también
escala, gana el escalamiento.

El hilo registra cómo terminó cada caso: resuelto por una persona, por el
agente (con su motivo), tras seguimientos sin respuesta o por el cierre por
inactividad. `AUTO_RESOLVE_AFTER_HOURS` (24 por defecto) queda como respaldo
para las conversaciones que ninguna regla cierra. Una conversación que tiene
una persona nunca se cierra automáticamente.

`GET`/`PUT /api/agents/{id}/follow-ups` recibe los tiempos en minutos
(`first_minutes`, `second_minutes`, `close_minutes`), un mensaje personalizado
por regla o nada para que lo redacte la IA (`first_text`, `second_text`,
`close_text`), `channels`, `enabled` y `resolve_enabled`. Un temporizador envía
lo pendiente cada `FOLLOW_UP_SWEEP_SECONDS` (60); con `0` se desactiva.

## El conocimiento en el prompt del sistema

Más allá de estos ajustes, los pares de preguntas y respuestas del agente, los documentos subidos, el contexto por cliente y el contexto por agente se ensamblan en el prompt del sistema al momento de responder. Consulta [Base de conocimiento](knowledge-base.md) para ver cómo se fragmentan, se generan embeddings y se recuperan los documentos.

## Despublicar y eliminar un agente

**Despublicar** (`is_active: false`) pausa el agente: deja de responder y de gastar tokens, los mensajes siguen llegando para una persona, y todo se conserva. **Eliminar** (`DELETE /api/agents/{id}`) borra su conocimiento, herramientas, preguntas y respuestas, reglas de escalamiento y configuración. Las conversaciones que atendió son el historial del cliente y se quedan en el portal con el nombre del agente. Un agente que atiende un canal no se puede eliminar hasta asignar otro agente a ese canal (`409`).
