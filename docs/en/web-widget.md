# Web chat widget

> Leer en español: [web-widget.md](../es/web-widget.md)

The web widget is an embeddable chat, a channel of a client answered by one of its agents, that you can drop onto any website with a single `<script>` tag. Visitors get a floating chat button; opening it talks to the agent through OpenLivery's public API, with the same knowledge and instructions you configured.

## How it works

The web chat is a channel of the client, like its WhatsApp lines: each client has at most one, and you choose which of the client's agents answers it. The channel carries a public id used in the widget route `/widget/<publicId>`. The loader script mounts an `iframe` pointing at that route and adds a floating launcher button.

The widget only works while the channel is enabled and the client is active: the backend serves the config, history and message endpoints only then. The public id belongs to the channel, not to the agent, so you can change or replace the agent without touching the sites where the snippet is embedded.

## Set it up and get the snippet

1. Open the client, go to **Channels** and pick **Web chat** (or use the Channels page and pick the client).
2. Choose the agent that answers, set the greeting, color and position (left or right), and keep **Enable web chat** on.
3. Save, then copy the embed snippet from the **Embed code** section. A **Preview** link opens the widget standalone.

The snippet points `data-agent` at the channel's public id and passes the appearance options as data attributes:

```html
<script
  src="https://your-openlivery-domain/widget.js"
  data-agent="CHANNEL_PUBLIC_ID"
  data-color="#075985"
  data-position="right"
  async
></script>
```

Paste it before the closing `</body>` tag of any page. The `src` origin must be your OpenLivery deployment; `widget.js` derives the iframe URL from its own origin.

## Messages and rate limiting

When a visitor sends a message, the widget calls the public endpoint `POST /api/widget/<publicId>/messages` with a per-browser `session_id`. The backend finds the channel and its agent, appends the message to a `widget` conversation, retrieves knowledge, calls the configured provider and returns the reply. Session history is kept in the visitor's `localStorage` so the conversation survives page reloads.

These public endpoints are rate-limited per client IP (30 message requests per minute) because each call spends LLM tokens. Callers over the limit get `429 Too Many Requests` with a `Retry-After` header. The limiter reads the client IP from `X-Forwarded-For` set by the gateway. See [Configuration](configuration.md) for the `RATE_LIMIT_ENABLED` toggle.

While open, the widget also polls `GET /api/widget/<publicId>/updates` every few seconds (its own, wider limit of 120 per minute), so replies written by a person who took over the conversation appear live, labelled with their name. Resolving a conversation closes the case: the visitor's next message opens a new one, and the widget keeps showing the whole exchange.

## Widget conversations in the inbox

Every widget chat becomes a conversation on the `widget` channel, so it shows up in the [Inbox](inbox.md) alongside WhatsApp and playground threads. You can filter by the widget channel, read the full transcript, and switch a conversation to **human** mode — which pauses the AI so an operator can reply directly from the portal.
