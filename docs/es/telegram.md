# Telegram

El agente de un cliente puede responder los chats privados de un bot de
Telegram. El bot se conecta con el token que entrega @BotFather; no hay que
crear una aplicación ni pasar una revisión. Las conversaciones aparecen en la
bandeja junto a los demás canales, y una persona puede tomar cualquiera.

## Crea el bot

1. Abre [@BotFather](https://t.me/BotFather) en Telegram y envía `/newbot`.
2. Elige el nombre visible del bot y un usuario que termine en `bot`.
3. Copia el token que te responde BotFather (`123456789:AA…`). Quien lo tenga
   controla el bot, así que trátalo como una contraseña.

## Conéctalo

Abre el cliente, luego **Canales** y **Telegram**. Elige el agente que
responde, si quieres un nombre para la bandeja, pega el token y pulsa
**Conectar bot**. OpenLivery revisa el token con Telegram, lo guarda cifrado y
apunta el webhook del bot a esta instalación. Un cliente puede conectar varios
bots; un bot pertenece a un solo cliente a la vez.

El webhook necesita un origen público con HTTPS. Se arma con
`SOCIAL_PUBLIC_URL`, o con `FRONTEND_URL` si está vacío; en una máquina local,
expón el stack con un túnel y pon su dirección en `SOCIAL_PUBLIC_URL` antes de
conectar. Si la dirección cambia después, abre el bot y pulsa **Revisar
conexión** para apuntar el webhook a la nueva.

## Qué maneja

- **Solo chats privados.** Los mensajes en grupos y canales se ignoran.
- **Sin ventana de respuesta.** La persona inicia el chat al abrir el bot
  (Telegram envía `/start`, que el agente lee como un chat recién abierto). Desde
  ahí, el agente y el equipo pueden responder cuando quieran.
- **Archivos en los dos sentidos.** Texto, fotos, notas de voz, audios, videos,
  documentos y stickers estáticos llegan a la bandeja, hasta los 20 MB que
  Telegram deja descargar a un bot. Las notas de voz se transcriben y las
  imágenes se describen cuando el agente tiene esas capacidades. Las respuestas
  pueden llevar archivos: fotos, notas de voz (las grabaciones del navegador se
  convierten a Ogg Opus), videos y documentos.
- **Formato.** Los agentes escriben en Markdown; la copia que sale a Telegram
  usa el formato propio de Telegram (negrita, cursiva, enlaces, código). Si
  Telegram rechaza el formato, la respuesta sale como texto plano.
- **Escribiendo.** Mientras el agente escribe, el chat muestra al bot
  escribiendo. Los bots no pueden marcar mensajes como leídos.
- Los seguimientos, el escalamiento, la captura de datos, los equipos y los
  resúmenes funcionan como en los demás canales.

## Cuando algo falla

- Un contacto que bloqueó el bot o borró el chat no puede recibir mensajes; la
  respuesta queda como no entregada y el bot sigue conectado.
- Un token revocado en BotFather detiene todas las respuestas y el bot indica
  que necesita un token nuevo. Pega el nuevo en **Token del bot** y guarda.
- **Desconectar** quita el webhook y el bot del cliente. Sus conversaciones
  quedan en la bandeja como historial; el bot sigue existiendo en Telegram.
