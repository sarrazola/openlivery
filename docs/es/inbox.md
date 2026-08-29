# Bandeja de entrada

> Read in English: [inbox.md](../en/inbox.md)

La bandeja de entrada (Inbox) es un único lugar para observar todas las conversaciones que mantienen tus agentes, buscar entre ellas e intervenir como humano cuando la IA necesita ayuda. Reúne las conversaciones de todos los canales — el playground, [WhatsApp](whatsapp.md) y el [widget web](web-widget.md) — en una sola lista.

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

Cada conversación lleva un campo `mode`. En modo **AI** el agente responde automáticamente. Usa **Tomar el control** para cambiar la conversación a modo **human**: esto pausa la IA para que un operador responda en su lugar. Mientras una conversación está en modo humano, la IA no genera respuestas — los intentos de hacerlo se rechazan hasta que la devuelvas. Cuando termines, **Devolver a la IA** vuelve a cambiar el modo y el agente reanuda.

Es el mismo concepto de `mode` usado en las conversaciones de [WhatsApp](whatsapp.md), por lo que tomar el control funciona de forma consistente sin importar el canal.

## Quién puede tomar el control

Tanto los operadores de la agencia (desde esta bandeja de entrada) como los usuarios del cliente pueden tomar el control de las conversaciones. Los usuarios del cliente lo hacen desde el [portal del cliente](client-portal.md), que expone las mismas acciones de tomar el control y responder como humano, acotadas a su cliente.
