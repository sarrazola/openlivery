<p align="center">
  <img src="apps/web/public/brand/openlivery-logo-original.png" width="88" alt="OpenLivery" />
</p>

<h1 align="center">OpenLivery</h1>

<p align="center">
  The open-source, white-label platform for agencies to build, run and manage AI agents for their clients.
</p>

<p align="center">
  <a href="https://openlivery.com/docs"><strong>Documentation</strong></a> ·
  <a href="https://openlivery.com/docs/getting-started">Quick start</a> ·
  <a href="https://openlivery.com/docs/self-hosting">Self-hosting</a> ·
  <a href="https://github.com/sarrazola/openlivery/discussions">Discussions</a>
</p>

<p align="center">
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-black" alt="MIT License" /></a>
  <img src="https://img.shields.io/badge/backend-FastAPI-009688" alt="FastAPI" />
  <img src="https://img.shields.io/badge/frontend-Next.js-black" alt="Next.js" />
  <img src="https://img.shields.io/badge/bridge-Baileys-25D366" alt="Baileys" />
</p>

---

OpenLivery is a multi-tenant workspace where an agency creates AI agents for its
clients, gives each client a branded portal, and talks to end users over
WhatsApp or an embeddable web chat widget. Bring your own OpenAI / Anthropic
keys and self-host the whole thing with one command.

## Documentation

Full documentation lives at **[openlivery.com/docs](https://openlivery.com/docs)**.

| Guide | What it covers |
| --- | --- |
| [Getting started](https://openlivery.com/docs/getting-started) | Run the stack with Docker and create your first agency |
| [Configuration](https://openlivery.com/docs/configuration) | Environment variables, secrets, ports and the gateway |
| [Architecture](https://openlivery.com/docs/architecture) | The services, the data model and tenant isolation |
| [Self-hosting](https://openlivery.com/docs/self-hosting) | Deploy to a server, back up, upgrade and troubleshoot |
| [Contributing](https://openlivery.com/docs/contributing) | Run the project locally, tests and conventions |
| [Push notifications](docs/push-notifications.md) | Optional, provider-agnostic notifications for the mobile app |
| [WhatsApp Cloud API](docs/connections/whatsapp-cloud-api.md) | Connect a number with the official Meta API, end to end ([en español](docs/connections/whatsapp-cloud-api.es.md)) |

## Features

**Agents** — [docs](https://openlivery.com/docs/agents)
- ✅ Instructions, personality, per-client & per-agent context, timezone, and temperature / max-tokens / memory controls
- ✅ Multimodal capabilities: **image recognition** (vision) and **audio transcription** for incoming media
- ✅ Creation wizard with a live token counter and industry starter templates

**Knowledge base** — [docs](https://openlivery.com/docs/knowledge-base)
- ✅ Manual context, structured **Q&A pairs** and PDF upload, with embedding-based semantic retrieval (keyword fallback)
- ✅ Portable JSON embeddings — no database extension required

**AI providers** — [docs](https://openlivery.com/docs/ai-providers)
- ✅ Bring-your-own **OpenAI** (Responses API) and **Anthropic** (Messages API) keys — agency-level, encrypted, and validated when saved
- ✅ Any OpenAI-compatible endpoint via per-connection base URL + model

**Custom tools** — [docs](https://openlivery.com/docs/custom-tools)
- ✅ Per-agent **HTTP tools**: any REST endpoint with path/query/body parameters, encrypted auth headers and an SSRF guard
- ✅ **MCP servers** (Streamable HTTP or SSE) with test-before-save connection checks and cached tool discovery
- ✅ Tool usage recorded per reply and surfaced in the playground, including failure details

**Channels** — [WhatsApp](https://openlivery.com/docs/whatsapp) · [Web widget](https://openlivery.com/docs/web-widget)
- ✅ **WhatsApp Cloud API** (official Meta API) — bring your own Meta app credentials, signed webhooks, per-client number
- ✅ **WhatsApp QR** through Baileys — QR link, per-client number, encrypted persistent session
- ✅ Embeddable **web chat widget** for any website
- 🚧 Instagram DM, Facebook Messenger *(planned)*

**Operations** — [Inbox](https://openlivery.com/docs/inbox) · [Client portal](https://openlivery.com/docs/client-portal) · [Dashboard](https://openlivery.com/docs/dashboard)
- ✅ Unified **Inbox** with server-side search, filter tabs, unread tracking, pagination and human takeover
- ✅ Per-client **portal** with its own login and Inbox, optionally served under the client's **own custom domain** (DNS-verified, automatic HTTPS)
- ✅ **Dashboard** with activity, top agents, token usage by model and a date-range filter
- ✅ Agency **white-label** (name, identifier, color, logo)

## Architecture

Three services plus PostgreSQL, orchestrated by Docker Compose:

| App | Stack | Role |
| --- | --- | --- |
| `apps/api` | FastAPI · SQLAlchemy · Alembic | REST API, data model, AI/knowledge/provider services |
| `apps/web` | Next.js · React · TypeScript · Tailwind | Agency dashboard, client portal, playground, widget |
| `apps/whatsapp` | Node.js · Baileys | WhatsApp Web bridge (stateful sessions) |

All data lives in PostgreSQL; provider keys and WhatsApp sessions are encrypted
at rest. Every query is scoped by `agency_id` for tenant isolation, and public
endpoints (sign-in and the web widget) are rate-limited per client IP. A Caddy
gateway serves the app and API from a single origin (`/api/*` → backend).

Read more in the [architecture guide](https://openlivery.com/docs/architecture).

## Quick start

Requires Docker (Desktop or Engine + Compose plugin).

```bash
git clone https://github.com/sarrazola/openlivery.git
cd openlivery
./scripts/generate-docker-env.sh   # random secrets in .env.docker (gitignored)
make up                            # build, start, migrate
```

Then open **http://localhost:3000** (API docs at **http://localhost:8000/docs**).
Ports clashing? `API_PORT=8001 WEB_PORT=3001 DB_PORT=5433 make up`.
Prefer not to build? `make pull` runs the prebuilt images published to GHCR.

The full walkthrough — first agency, provider keys, agents, knowledge and
channels — is in the **[getting started guide](https://openlivery.com/docs/getting-started)**.
Deploying to a public server (reverse proxy, TLS, backups) is covered in
**[self-hosting](https://openlivery.com/docs/self-hosting)**.

## Community & support

- **[GitHub Discussions](https://github.com/sarrazola/openlivery/discussions)** — questions, ideas and help building with OpenLivery.
- **[GitHub Issues](https://github.com/sarrazola/openlivery/issues)** — bugs and feature requests.

## Project structure

```text
apps/
  api/         FastAPI backend (app/, migrations/, tests/)
  web/         Next.js frontend (app/, components/, lib/, types/)
  whatsapp/    Baileys WhatsApp bridge (src/)
  mobile/      Optional Expo app for the businesses you serve (unbranded)
docs/          Self-hosting and operations guide
scripts/       Helper scripts (generate-docker-env.sh)
Makefile       Common commands (make help)
docker-compose.yml
```

## The mobile app

`apps/mobile` is an optional Expo app: the inbox a business you serve carries in
their pocket, with conversations, takeover, replies, photos and voice notes. It
is not installed with the platform and the server does not need it — nobody
running OpenLivery has to build or deploy it to have everything working.

It deliberately carries **no brand**: no name, no logo, no bundle identifier, no
preset pointing at any hosted service. What ships is a working app and the
machinery to make it yours — put your identity in a brand file, build, and
publish it under your own name from your own developer account. The whole
checklist, including why you publish it rather than us, is in
[apps/mobile/WHITELABEL.md](apps/mobile/WHITELABEL.md).

## Contributing

Run the project locally, the test suites and the conventions are documented in
the **[contributing guide](https://openlivery.com/docs/contributing)**. In short:
all code, identifiers, comments and docs are in English; end-user UI is localized
(English default, Spanish) through the typed i18n system in `apps/web/lib/i18n`.

## License

[MIT](./LICENSE).
