<p align="center">
  <img src="apps/web/public/brand/openlivery-logo-original.png" width="88" alt="OpenLivery" />
</p>

<h1 align="center">OpenLivery</h1>

<p align="center">
  The open-source, white-label platform for agencies to build, run and manage AI agents for their clients.
</p>

<p align="center">
  <a href="docs/en/"><strong>Documentation</strong></a> ·
  <a href="docs/es/"><strong>Documentación</strong></a> ·
  <a href="docs/en/getting-started.md">Quick start</a> ·
  <a href="docs/en/self-hosting.md">Self-hosting</a> ·
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

Full documentation lives in **[docs/](docs/)**. Every guide is written twice:
**[English](docs/en/)** and **[Spanish](docs/es/)**, same filename under each.

| Guide | What it covers |
| --- | --- |
| [Getting started](docs/en/getting-started.md) | Run the stack with Docker and create your first agency |
| [Configuration](docs/en/configuration.md) | Environment variables, secrets, ports and the gateway |
| [Architecture](docs/en/architecture.md) | The services, the data model and tenant isolation |
| [Self-hosting](docs/en/self-hosting.md) | Deploy to a server, back up, upgrade and troubleshoot |
| [Contributing](docs/en/contributing.md) | Run the project locally, tests and conventions |
| [Push notifications](docs/en/push-notifications.md) | Optional, provider-agnostic notifications for the mobile app |
| [WhatsApp Cloud API](docs/en/whatsapp-cloud-api.md) | Connect a number with the official Meta API, end to end |

## Features

**Agents** — [docs](docs/en/agents.md)
- ✅ Instructions, personality, per-client & per-agent context, timezone, and temperature / max-tokens / memory controls
- ✅ Multimodal capabilities: **image recognition** (vision) and **audio transcription** for incoming media
- ✅ Creation wizard with a live token counter and industry starter templates

**Knowledge base** — [docs](docs/en/knowledge-base.md)
- ✅ Manual context, structured **Q&A pairs** and PDF upload, with embedding-based semantic retrieval (keyword fallback)
- ✅ Portable JSON embeddings — no database extension required

**AI providers** — [docs](docs/en/ai-providers.md)
- ✅ Bring-your-own **OpenAI** (Responses API) and **Anthropic** (Messages API) keys — agency-level, encrypted, and validated when saved
- ✅ Any OpenAI-compatible endpoint via per-connection base URL + model

**Custom tools** — [docs](docs/en/custom-tools.md)
- ✅ Per-agent **HTTP tools**: any REST endpoint with path/query/body parameters, encrypted auth headers and an SSRF guard
- ✅ **MCP servers** (Streamable HTTP or SSE) with test-before-save connection checks and cached tool discovery
- ✅ Tool usage recorded per reply and surfaced in the playground, including failure details

**Channels** — [WhatsApp Cloud API](docs/en/whatsapp-cloud-api.md) · [WhatsApp QR](docs/en/whatsapp.md) · [Web widget](docs/en/web-widget.md)
- ✅ **WhatsApp Cloud API** (official Meta API) — bring your own Meta app credentials, signed webhooks, per-client number
- ✅ **WhatsApp QR** through Baileys — QR link, per-client number, encrypted persistent session
- ✅ Embeddable **web chat widget** for any website
- 🚧 Instagram DM, Facebook Messenger *(planned)*

**Operations** — [Inbox](docs/en/inbox.md) · [Client portal](docs/en/client-portal.md) · [Dashboard](docs/en/dashboard.md)
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

Read more in the [architecture guide](docs/en/architecture.md).

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
channels — is in the **[getting started guide](docs/en/getting-started.md)**.
Deploying to a public server (reverse proxy, TLS, backups) is covered in
**[self-hosting](docs/en/self-hosting.md)**.

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
the **[contributing guide](docs/en/contributing.md)**. In short:
all code, identifiers, comments and docs are in English; end-user UI is localized
(English default, Spanish) through the typed i18n system in `apps/web/lib/i18n`.

## License

[MIT](./LICENSE).
