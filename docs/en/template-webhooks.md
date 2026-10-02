# Template webhooks

> Leer en español: [template-webhooks.md](../es/template-webhooks.md)

A template webhook is an address another system calls to send an approved
WhatsApp template to a contact: an appointment reminder, an order notice, a
payment confirmation. The message is stored as the agent's, so when the contact
answers, the agent replies knowing what was sent.

It needs a client with a [WhatsApp Cloud API](whatsapp-cloud-api.md) number and
at least one approved template.

## Create one

1. Open the client and go to **Webhooks**.
2. **New webhook**: give it a name, choose the WhatsApp number and the template.
   The form shows the variables the template takes.
3. Save. The row shows the address, the secret and an example call to copy.

The secret is shown once, when the webhook is created. Only its last characters
stay visible afterwards. If it is lost or exposed, **Regenerate** makes a new
one and the old one stops working right away.

The agent assigned to the number is the one that answers the contact. A webhook
can be turned off, edited or deleted; a deleted or turned off webhook stops
accepting calls right away.

## Call it

`POST` a JSON body to the address, with the secret as a bearer in the
`Authorization` header. The address identifies the webhook and is not a
secret: without the header it sends nothing.

```bash
curl -X POST https://your-domain/api/public/hooks/<webhook-id> \
  -H "Authorization: Bearer whk_..." \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "573001112233",
    "name": "Ana",
    "variables": {"nombre": "Ana", "fecha": "Tuesday 7", "hora": "3 pm"},
    "context": "Appointment 123, general check-up",
    "idempotency_key": "appointment-123-reminder"
  }'
```

| Field | Required | What it is |
| --- | --- | --- |
| `phone` | yes | The contact's number with country code. Spaces, dashes and `+` are ignored. |
| `variables` | when the template has them | The body values by variable name. A positional template takes `"1"`, `"2"` and so on. |
| `name` | no | The contact's name, used only when the phone is new to the client. |
| `header` | when the template has one | The header's variable, or the `https://` link of its image, video or document. |
| `location` | for a location header | `latitude`, `longitude`, and optionally `name` and `address`. |
| `buttons` | for dynamic buttons | One value per button, in order; only the dynamic ones are read. |
| `context` | no | Notes for the agent that the contact never sees: an id, a detail the template's text does not carry. |
| `idempotency_key` | no | A retry carrying the same key answers with the first send's result and sends nothing. |

The answer says where the message went:

```json
{
  "conversation_id": "…",
  "message_id": "…",
  "mode": "ai",
  "started": true,
  "duplicate": false,
  "text": "Hola Ana, tu cita es el Tuesday 7 a las 3 pm."
}
```

`mode` is who answers when the contact replies: `ai` or `human`.

## What happens to the conversation

- A template is always what goes out, whether or not the 24-hour reply window
  is open, so a call behaves the same every time.
- If the contact has an open conversation on that number, the message joins it.
  Otherwise a new one starts, handled by the number's agent. A contact whose
  tag routes to a team starts in that team's hands, as when they write first.
- A conversation a person is handling stays with that person: the template is
  sent and shown in the thread, and `mode` comes back as `human`.
- The send does not start the agent's inactivity follow-ups. A conversation
  nobody answers is closed by the usual idle rule.

## Errors

| Status | Meaning |
| --- | --- |
| `401` | The secret is missing or wrong. |
| `404` | No webhook has that address. |
| `409` | The webhook, its number or the client is turned off, or the template is no longer approved. |
| `422` | The phone is not a number, or a variable is missing; the message names which. |
| `429` | Too many calls in a minute from one address. |
| `502` | WhatsApp refused the send; the message carries its reason. Nothing is stored. |
