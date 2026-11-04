# Web chat widget

> Leer en español: [web-widget.md](../es/web-widget.md)

The web widget is an embeddable chat, a channel of a client answered by one of its agents, that you can drop onto any website with a single `<script>` tag. Visitors get a floating chat button, or a card placed inside the page itself; either way they talk to the agent through OpenLivery's public API, with the same knowledge and instructions you configured.

## How it works

The web chat is a channel of the client, like its WhatsApp lines: each client has at most one, and you choose which of the client's agents answers it. The channel carries a public id used in the widget route `/widget/<publicId>`. The loader script mounts an `iframe` pointing at that route and, unless the chat sits inside the page, adds a floating launcher button.

The widget only works while the channel is enabled and the client is active: the backend serves the config, history and message endpoints only then. The public id belongs to the channel, not to the agent, so you can change or replace the agent without touching the sites where the snippet is embedded.

## Set it up and get the snippet

1. Open the client, go to **Channels** and pick **Web chat**.
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

## Place the chat inside a page

Set **How it shows** to **Inside the page** and the embed code changes to a container and the script:

```html
<div id="openlivery-chat"></div>
<script
  src="https://your-openlivery-domain/widget.js"
  data-agent="CHANNEL_PUBLIC_ID"
  data-mode="inline"
  data-target="#openlivery-chat"
  async
></script>
```

There is no launcher and nothing floats: the chat takes the width of its container, starts as a compact card and grows into the full chat at the first message. The rest of the page moves down to make room.

| Attribute | Meaning |
| --- | --- |
| `data-mode` | `inline` places the chat in the page. Left out, it is the floating bubble. |
| `data-target` | CSS selector of the element to fill. Left out, or matching nothing, the chat appears where the script tag is. |
| `data-height` | Height of the open chat in pixels, 560 by default. It never exceeds the visitor's screen. |

The mode lives in the snippet, not in the channel, so one client can have the bubble across its site and the card on a single page. While the channel is off or unavailable the frame hides itself and leaves no gap. To place two chats on one page, give each container its own `id` and point each script's `data-target` at it.

## Chat start and appearance

**Chat start** sets what the visitor sees before writing: a main question, the greeting, up to six suggestions, the header title and subtitle, the text inside the message box and a footer note. Every one of them is optional, and a suggestion is sent as the visitor's own message when tapped. **Appearance** sets the color, the background, the header (with color or light), the title font and the corners. These apply to the bubble and to the card alike.

The chat runs inside an `iframe`, so it does not inherit the fonts or styles of the site around it. Those options are the way to bring it close to the page.

## Messages and rate limiting

When a visitor sends a message, the widget calls the public endpoint `POST /api/widget/<publicId>/messages` with a per-browser `session_id`. The backend finds the channel and its agent, appends the message to a `widget` conversation, retrieves knowledge, calls the configured provider and returns the reply. Session history is kept in the visitor's `localStorage` so the conversation survives page reloads.

These public endpoints are rate-limited per client IP (30 message requests per minute) because each call spends LLM tokens. Callers over the limit get `429 Too Many Requests` with a `Retry-After` header. The limiter reads the client IP from `X-Forwarded-For` set by the gateway. See [Configuration](configuration.md) for the `RATE_LIMIT_ENABLED` toggle.

While open, the widget also polls `GET /api/widget/<publicId>/updates` every few seconds (its own, wider limit of 120 per minute), so replies written by a person who took over the conversation appear live, labelled with their name. Resolving a conversation closes the case: the visitor's next message opens a new one, and the widget shows the new case on its own; earlier chats stay one tap away behind the history button, read-only. They are tied to the anonymous session id in the browser's storage and live on the server, so a reload keeps them and only clearing site data loses them.

## Widget conversations in the inbox

Every widget chat becomes a conversation on the `widget` channel, so it shows up in the [Inbox](inbox.md) alongside WhatsApp and playground threads. You can filter by the widget channel, read the full transcript, and switch a conversation to **human** mode — which pauses the AI so an operator can reply directly from the portal.
