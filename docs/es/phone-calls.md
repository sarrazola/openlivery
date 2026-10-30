# Llamadas telefónicas

> Read in English: [phone-calls.md](../en/phone-calls.md)

Un **agente de voz** contesta el número de teléfono de un cliente. ElevenLabs Agents atiende cada llamada: escucha a quien llama, decide cuándo terminó o lo interrumpió, piensa con uno de sus propios modelos y habla con la voz del agente. OpenLivery es donde se configura el agente. Escribe en ElevenLabs las instrucciones, los datos del negocio, las preguntas frecuentes, el saludo, la voz, el modelo y las herramientas del agente, y los vuelve a escribir cada vez que cambian, así que un turno de la llamada nunca espera a OpenLivery. El número sigue en tu operador telefónico, Twilio o Telnyx, y queda apuntando a ElevenLabs cuando agregas la línea.

Cada llamada se vuelve una conversación en la bandeja, en el canal **Teléfono**, con su transcripción, duración, costo y un resumen.

## Qué necesitas

En **Ajustes**, sección **Llamadas telefónicas**:

- **ElevenLabs**: una llave de API con permiso de escritura en Agents, Voices y Webhooks. Al guardarla se comprueba con ElevenLabs y se dice qué permiso le falta, si le falta alguno. ElevenLabs cobra los minutos y el modelo a esa cuenta.
- **Operador telefónico**: el Account SID y el Auth Token de **Twilio**, o una llave de API de **Telnyx**. Los números que ya tienes ahí aparecen al agregar una línea. El operador cobra las llamadas a esa cuenta.

OpenLivery debe estar accesible desde internet por HTTPS, porque ElevenLabs lo llama durante y después de cada llamada. Usa `PHONE_PUBLIC_URL`, o `FRONTEND_URL` si está vacía (ver [configuración](configuration.md)).

## El agente de voz

Créalo en **Agentes › Nuevo agente** y elige **Voz**. Un agente de voz tiene las mismas instrucciones, datos del negocio, conocimiento, datos de contacto por pedir y herramientas que uno de chat, y además:

- **Voz**: pega el ID de cualquier voz de la biblioteca de voces de ElevenLabs (abre el menú de la voz y elige *Copy voice ID*). La tarjeta reproduce la muestra de la voz. Sin una, el agente habla con una voz conversacional en su idioma.
- **Saludo**: se dice palabra por palabra apenas se contesta la llamada.
- **Modelo**: **Realtime Mini** (el predeterminado, el que responde más rápido), **Realtime Max** (razona antes de responder, para instrucciones largas) o **Gemini 3.8 Flash**. Todos corren en ElevenLabs junto a la voz.
- **Pasar la llamada a una persona**: un número, con su país, y cuándo pasar la llamada. Quien llama sigue en la línea mientras se transfiere. Si queda vacío, el agente le dice que alguien lo va a llamar y deja el caso a una persona en la bandeja.

El horario del agente, los seguimientos y el playground no aplican a las llamadas: el teléfono se contesta a cualquier hora.

## Agregar una línea

En **Canales** del cliente, agrega un número de teléfono: elige el agente de voz y uno de los números del operador. OpenLivery crea el agente de la línea en ElevenLabs, importa allí el número (uno de Twilio directamente, uno de Telnyx por una conexión SIP que crea) y la línea queda **Conectada**. Si algo falla, la línea dice por qué y **Conectar de nuevo** lo reintenta.

## Durante la llamada

Cuando entra una llamada, antes del saludo, ElevenLabs le pregunta a OpenLivery quién llama. El agente recibe lo que sabría en el chat: el contacto del cliente para ese número con los datos ya guardados, los datos que aún tiene que pedir y un resumen de su último caso. Los contactos son de cada cliente, así que un número conocido por un cliente es un contacto nuevo para otro. La conversación se abre en ese momento, así que la llamada aparece en la bandeja mientras suena. ElevenLabs documenta esta consulta para números de Twilio; en una llamada que no la hace, el agente empieza sin ese contexto.

Durante la llamada el agente puede usar herramientas, cada una es una petición de ElevenLabs a OpenLivery:

- **Conocimiento**: los documentos cortos van en el prompt del agente. Cuando suman más de unos 16.000 caracteres, el agente los consulta con `search_knowledge`.
- **Datos del contacto**: `save_contact_field` guarda lo que dice quien llama (su nombre, su correo o uno de los campos propios del cliente) en su contacto, igual que en el chat.
- **Pasar a una persona**: sin número de transferencia, `escalate_to_human` deja el caso abierto para el equipo, asignado como la escalada asigna los chats, y la conversación no se cierra al colgar.
- **Las herramientas propias del agente**: sus herramientas HTTP y servidores MCP ([herramientas personalizadas](custom-tools.md)) también funcionan en llamadas. Mientras corre una herramienta lenta, la voz dice algo natural para que la línea nunca quede en silencio.

Cada petición lleva un secreto que ElevenLabs guarda entre los secretos del espacio de trabajo; OpenLivery guarda solo su hash.

## Al terminar la llamada

ElevenLabs reporta la llamada terminada, firmada con el secreto del webhook. La conversación recibe la transcripción, cada turno en el momento en que se dijo, con las herramientas que usó el agente, y la duración, el motivo de cierre y el resumen de la llamada. El costo (los minutos de voz y el modelo, en USD) queda como un registro de uso con propósito `call`, así que los [reportes](reports.md) lo listan junto a las respuestas del chat. La conversación se cierra, salvo que la tenga una persona. Una llamada que nunca conecta cierra su conversación con el motivo.

Cada llamada es su propia conversación, nunca una respuesta en un caso abierto. No se guarda el audio.

## La línea al día

Un cambio en algo que lleva la línea se escribe solo en ElevenLabs: las instrucciones, los datos del negocio, la voz, el saludo, el modelo y el número de transferencia del agente, el nombre y la zona horaria del cliente y, un par de segundos después de la última edición, sus documentos, preguntas frecuentes, herramientas, datos de contacto y reglas de escalada. Una herramienta que no cambió no se vuelve a escribir.

## Límites

- Una cuenta de ElevenLabs y una cuenta por operador por agencia.
- Solo llamadas entrantes.
- El horario del agente no aplica a las llamadas.
