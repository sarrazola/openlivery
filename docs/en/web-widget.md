# Web chat widget

> Leer en español: [web-widget.md](../es/web-widget.md)

The web widget is an embeddable chat, backed by one of your agents, that you can drop onto any website with a single `<script>` tag. Visitors get a floating chat button; opening it talks to the agent through OpenLivery's public API, with the same knowledge and instructions you configured.

## How it works

Each agent has a `widget_public_id` — a public identifier used in the widget route `/widget/<publicId>`. The loader script mounts an `iframe` pointing at that route and adds a floating launcher button. Because the id is public, the widget is served without authentication, so nothing sensitive (API keys, other clients' data) is ever exposed to the browser.

The widget only works while it is enabled: the backend serves the config, history and message endpoints only for agents where `widget_enabled` is on. Publish and enable the agent before embedding.

## Enable and get the snippet

1. Open the agent and go to the **Widget** tab.
2. Toggle **Enable widget** and set the greeting, color and position (left or right).
3. Save, then copy the embed snippet from the **Embed** section. A **Preview** link opens the widget standalone.

The snippet points `data-agent` at the agent's public id and passes the appearance options as data attributes:

```html
<script
  src="https://your-openlivery-domain/widget.js"
  data-agent="AGENT_PUBLIC_ID"
  data-color="#075985"
  data-position="right"
  async
></script>
```

Paste it before the closing `</body>` tag of any page. The `src` origin must be your OpenLivery deployment; `widget.js` derives the iframe URL from its own origin.

## Messages and rate limiting

When a visitor sends a message, the widget calls the public endpoint `POST /api/widget/<publicId>/messages` with a per-browser `session_id`. The backend finds the agent, appends the message to a `widget` conversation, retrieves knowledge, calls the configured provider and returns the reply. Session history is kept in the visitor's `localStorage` so the conversation survives page reloads.

These public endpoints are rate-limited per client IP (30 message requests per minute) because each call spends LLM tokens. Callers over the limit get `429 Too Many Requests` with a `Retry-After` header. The limiter reads the client IP from `X-Forwarded-For` set by the gateway. See [Configuration](configuration.md) for the `RATE_LIMIT_ENABLED` toggle.

## Widget conversations in the inbox

Every widget chat becomes a conversation on the `widget` channel, so it shows up in the [Inbox](inbox.md) alongside WhatsApp and playground threads. You can filter by the widget channel, read the full transcript, and switch a conversation to **human** mode — which pauses the AI so an operator can reply directly from the portal.
