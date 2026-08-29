# Custom tools

> Leer en español: [custom-tools.md](../es/custom-tools.md)

Custom tools let an agent act, not just answer. From the **Tools** tab of the agent editor you can connect two kinds of tools, and the agent decides when to call them during a conversation: **HTTP tools** (an endpoint of your own or any REST API) and **MCP servers** (external services that speak the Model Context Protocol). Tools work on every channel: the playground, the web widget and WhatsApp.

## HTTP tools

An HTTP tool describes one endpoint the agent may call:

- **Tool name** — `snake_case`, used as the function name the model sees (for example `check_order`). Consecutive underscores are not allowed.
- **Endpoint URL and method** — the URL may contain `{param}` placeholders (for example `https://api.example.com/orders/{order_id}`); each placeholder automatically becomes a required input the model must provide. Methods: GET, POST, PUT, PATCH or DELETE.
- **Prompt instructions** — tell the agent when and how to use the tool. This text is appended to the tool description the model sees, so be specific about the conditions and the data required.
- **Body and query parameters** — each parameter has a name, a type (`string`, `number`, `integer`, `boolean`), a description and a required flag. Body parameters are only allowed on POST, PUT and PATCH.
- **Advanced options** — auth headers (for example `Authorization: Bearer …`) and a timeout between 1 and 120 seconds (default 30). Header values are **encrypted at rest** and never returned by the API or shown in the UI again; you can only replace them.

When the model calls the tool, OpenLivery substitutes the path placeholders, sends the declared query parameters and JSON body, and returns the response to the model as `HTTP <status>: <body>`. Responses are capped at 100 KB.

## MCP servers

An MCP server connects the agent to every tool that server exposes:

- **Server name** — `snake_case`, up to 24 characters. The server's tools are exposed to the model as `<server>__<tool>` (for example `weather__get_forecast`), which keeps names collision-free across servers.
- **Server URL and transport** — Streamable HTTP or SSE.
- **Auth headers** — optional, encrypted at rest like HTTP tool headers.

Before you can save a server you must run **Test connection**, which connects, performs the MCP handshake and lists the server's tools. The discovered list is cached on save and reused at chat time, so conversations never wait on discovery; editing the URL, transport or headers re-runs the check. Creating or updating a server whose connection fails is rejected.

## How tool calling works

When an agent with enabled tools receives a message, OpenLivery sends the tool definitions to the model along with the conversation. If the model decides to call a tool, OpenLivery executes it (the HTTP request, or a call proxied to the MCP server), feeds the result back, and lets the model continue — up to **5 rounds** per reply, after which the model must answer with text. Works with both providers: OpenAI (Responses API) and Anthropic (Messages API). Token usage across all rounds is summed into the reply's usage record.

Every assistant reply stores which tools ran, with their arguments and a preview of each result. In the playground you will see a chip under the reply listing the tools used; failed calls are highlighted and show the error detail, so you can diagnose a broken tool without reading logs.

If a tool call fails, the agent is instructed to tell the user the information or action is not available right now — it will not silently answer from its own knowledge.

## Security

- **Private networks are blocked by default.** HTTP tool URLs that resolve to private, loopback or reserved addresses (including cloud metadata endpoints) are rejected at request time. Self-hosted deployments that need tools against internal services can opt out with `TOOLS_ALLOW_PRIVATE_URLS=true`.
- **Redirects are never followed.** A 3xx response counts as a failed call, since the data was not retrieved and following redirects blindly would bypass the address check.
- **Secrets stay encrypted.** Auth headers are encrypted with the same `ENCRYPTION_KEY` used for provider keys (see [Configuration](configuration.md)) and are never sent back to the browser.

## Troubleshooting

- **"Could not connect to the MCP server"** — the message includes the cause: rejected credentials (check the `Authorization` header format, usually `Bearer <token>`), unreachable host, timeout, or an endpoint that does not answer like an MCP server (check the URL and transport).
- **The agent never calls the tool** — make the prompt instructions concrete ("Use when the customer asks about an order status"), check the tool's toggle is enabled, and mention the data in your test message ("what's the status of order 42?").
- **A working tool suddenly fails** — the target API may have moved behind a redirect or changed auth. The playground error detail shows the exact status the tool received.

See [Agents](agents.md) for the rest of the agent editor and [AI providers](ai-providers.md) for connecting a model that supports tool calling.
