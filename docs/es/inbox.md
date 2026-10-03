# Bandeja de entrada

> Read in English: [inbox.md](../en/inbox.md)

La bandeja de entrada (Inbox) es un único lugar para observar todas las conversaciones que mantienen tus agentes y buscar entre ellas. Es una vista de lectura: tomar una conversación y responderla corresponde al equipo del cliente, desde el [portal del cliente](client-portal.md). Reúne las conversaciones de todos los canales — el playground, [WhatsApp](whatsapp.md) y el [widget web](web-widget.md) — en una sola lista.

## Lista unificada

Cada conversación muestra el nombre del contacto (o el título), una vista previa del último mensaje, el agente que la atiende, el canal por el que llegó y una etiqueta que indica si está en modo **AI** o **human**. La lista está acotada a tu agencia, por lo que los operadores solo ven las conversaciones de su propio inquilino.

Dos filtros en la parte superior acotan la vista: por **agente** y por **canal** (playground, WhatsApp o widget). Estos se combinan con las pestañas y la búsqueda de abajo.

## Búsqueda y pestañas

El cuadro de búsqueda funciona **del lado del servidor**: coincide con el título de la conversación, el nombre del contacto y el contenido del último mensaje. La entrada tiene un retardo (debounce), así que los resultados se actualizan poco después de dejar de escribir.

Cuatro pestañas filtran la lista:

- **All** — todas las conversaciones.
- **Unread** — conversaciones cuyo último mensaje es del visitante y no se ha leído desde entonces.
- **Human** — conversaciones actualmente en modo humano.
- **AI** — conversaciones que atiende el agente en ese momento.

## Seguimiento de no leídos y paginación

El estado de no leído se deriva de una marca de tiempo `operator_read_at`: una conversación cuenta como no leída cuando su último mensaje proviene del visitante y llegó después de la última vez que la abriste. Abrir una conversación la marca como leída. La primera página se refresca automáticamente cada pocos segundos para que los mensajes nuevos aparezcan sin recargar a mano. La lista se carga en páginas de 30 y trae más a medida que te desplazas hacia el final.

## Toma de control humana

Cada conversación lleva un campo `mode`. En modo **AI** el agente responde automáticamente. En modo **human** la IA queda en pausa y una persona responde en su lugar; los intentos de la IA por contestar se rechazan hasta que la conversación se devuelve. La bandeja muestra en qué modo está cada conversación.

Es el mismo concepto de `mode` usado en las conversaciones de [WhatsApp](whatsapp.md), por lo que funciona de forma consistente sin importar el canal.

## Quién puede tomar el control

Tomar una conversación, responderla y asignarla se hace desde el [portal del cliente](client-portal.md), por los usuarios del cliente y acotado a su cliente. La bandeja de la agencia no expone esas acciones: es donde la agencia lee. Si necesitas responder por un cliente, crea un usuario en el portal de ese cliente y trabaja desde ahí.
