# Webhooks de plantilla

> Read in English: [template-webhooks.md](../en/template-webhooks.md)

Un webhook de plantilla es una dirección que otro sistema llama para enviar a
un contacto una plantilla aprobada de WhatsApp: un recordatorio de cita, un
aviso de pedido, una confirmación de pago. El mensaje se guarda como del
agente, así que cuando el contacto responde, el agente contesta sabiendo qué
se envió.

Necesita un cliente con un número de [WhatsApp Cloud API](whatsapp-cloud-api.md)
y al menos una plantilla aprobada.

## Crear uno

1. Abre el cliente y ve a **Webhooks**.
2. **Nuevo webhook**: ponle un nombre, elige el número de WhatsApp y la
   plantilla. El formulario muestra las variables que lleva la plantilla.
3. Guarda. La fila muestra la dirección, el secreto y una llamada de ejemplo
   para copiar.

El secreto se muestra una sola vez, al crear el webhook. Después solo quedan
visibles sus últimos caracteres. Si se pierde o queda expuesto, **Regenerar**
crea uno nuevo y el anterior deja de funcionar de inmediato.

El agente asignado al número es el que le responde al contacto. Un webhook se
puede desactivar, editar o eliminar; uno eliminado o desactivado deja de
aceptar llamadas de inmediato.

## Llamarlo

Envía un `POST` con un cuerpo JSON a la dirección, con el secreto como bearer
en el encabezado `Authorization`. La dirección identifica el webhook y no es
un secreto: sin el encabezado no envía nada.

```bash
curl -X POST https://tu-dominio/api/public/hooks/<id-del-webhook> \
  -H "Authorization: Bearer whk_..." \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "573001112233",
    "name": "Ana",
    "variables": {"nombre": "Ana", "fecha": "martes 7", "hora": "3 pm"},
    "context": "Cita 123, consulta general",
    "idempotency_key": "cita-123-recordatorio"
  }'
```

| Campo | Obligatorio | Qué es |
| --- | --- | --- |
| `phone` | sí | El número del contacto con código de país. Se ignoran espacios, guiones y `+`. |
| `variables` | si la plantilla las tiene | Los valores del cuerpo por nombre de variable. Una plantilla posicional lleva `"1"`, `"2"`, etc. |
| `name` | no | El nombre del contacto; solo se usa si el teléfono es nuevo para el cliente. |
| `header` | si la plantilla tiene encabezado | La variable del encabezado, o el enlace `https://` de su imagen, video o documento. |
| `location` | para encabezado de ubicación | `latitude`, `longitude` y, opcionalmente, `name` y `address`. |
| `buttons` | para botones dinámicos | Un valor por botón, en orden; solo se leen los dinámicos. |
| `context` | no | Notas para el agente que el contacto nunca ve: un id, un detalle que el texto de la plantilla no trae. |
| `idempotency_key` | no | Un reintento con la misma clave responde con el resultado del primer envío y no envía nada. |

La respuesta dice a dónde fue el mensaje:

```json
{
  "conversation_id": "…",
  "message_id": "…",
  "mode": "ai",
  "started": true,
  "duplicate": false,
  "text": "Hola Ana, tu cita es el martes 7 a las 3 pm."
}
```

`mode` es quién responde cuando el contacto escriba: `ai` o `human`.

## Qué pasa con la conversación

- Siempre sale una plantilla, esté o no abierta la ventana de respuesta de
  24 horas, para que la llamada se comporte igual cada vez.
- Si el contacto tiene una conversación abierta en ese número, el mensaje entra
  ahí. Si no, empieza una nueva, atendida por el agente del número. Un contacto
  con una etiqueta que enruta a un equipo empieza en manos de ese equipo, igual
  que cuando escribe primero.
- Una conversación que atiende una persona se queda con esa persona: la
  plantilla se envía y se ve en el hilo, y `mode` vuelve como `human`.
- El envío no inicia los seguimientos por inactividad del agente. Una
  conversación que nadie responde se cierra por la regla de inactividad
  habitual.

## Errores

| Estado | Significado |
| --- | --- |
| `401` | Falta el secreto o es incorrecto. |
| `404` | Ningún webhook tiene esa dirección. |
| `409` | El webhook, su número o el cliente están desactivados, o la plantilla ya no está aprobada. |
| `422` | El teléfono no es un número, o falta una variable; el mensaje dice cuál. |
| `429` | Demasiadas llamadas en un minuto desde una misma dirección. |
| `502` | WhatsApp rechazó el envío; el mensaje trae el motivo. No se guarda nada. |
