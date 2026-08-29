# WhatsApp

> Leer en español: [whatsapp.md](../es/whatsapp.md)

OpenLivery connects a real WhatsApp number to each client so their agent answers conversations automatically. Each client gets its own session, linked by scanning a QR code from the WhatsApp mobile app — no WhatsApp Business API account required.

## The bridge service

WhatsApp support runs in a dedicated service, the **bridge** (`apps/whatsapp/`), a stateful Node.js process built on [Baileys](https://github.com/WhiskeySockets/Baileys), the WhatsApp Web protocol. The bridge holds one live socket per connected client and talks to the backend over an internal API.

Because it is stateful, the bridge does not keep sessions in memory only: the encrypted session and auth state is persisted through the backend in PostgreSQL. On startup the bridge calls the backend for the list of enabled channels that already have a saved session and reloads them, so numbers reconnect on their own after a restart.

## Connect a number

One WhatsApp session belongs to one client. To connect it:

1. Open a **client**, go to its **WhatsApp** channel, and pick the agent that should answer incoming messages.
2. Click connect. The backend asks the bridge to start a session, and a **QR code** appears.
3. On the phone that owns the number, open WhatsApp and go to **Settings → Linked devices → Link a device**.
4. Scan the QR code. Once the phone confirms, the channel switches to **connected** and shows the linked number.

The session survives restarts from then on. If the number is unlinked from the phone (or the session is invalidated), the bridge clears the stored auth state and the channel returns to disconnected. You can also disconnect from the same page, which logs the device out and removes the saved session.

## How messages flow

When a contact writes to the number:

1. The bridge receives the message and forwards it to the backend at `POST /api/whatsapp/channels/{channel_id}/inbound`.
2. The backend records the message on the client's conversation, retrieves the agent's knowledge, and generates a reply with the assigned agent.
3. The reply is sent back through the bridge to the contact on WhatsApp.

Images and voice notes are forwarded too; when the agent has image or audio understanding enabled they are described or transcribed before reaching the model. See [Knowledge base](knowledge-base.md).

Backend and bridge authenticate every call to each other with a shared secret, `WHATSAPP_BRIDGE_TOKEN`. It is generated for you by the setup script — see [Configuration](configuration.md).

## Human takeover

Every conversation has a `mode`, either `ai` (the default) or `human`. When you switch a conversation to human mode, the AI stops replying to it — the backend still records incoming messages, but generates no automatic answer — so a person can take over and respond directly from the [inbox](inbox.md) or the [client portal](client-portal.md). Switch back to `ai` to hand the conversation to the agent again.

## Other channels

WhatsApp is the only messaging channel in the open-source core today. Instagram and Facebook Messenger are on the roadmap.

Next: manage live conversations in the [inbox](inbox.md), or let clients handle their own in the [client portal](client-portal.md).
