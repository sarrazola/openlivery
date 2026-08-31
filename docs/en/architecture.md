# Architecture

> Leer en español: [architecture.md](../es/architecture.md)

OpenLivery is a multi-tenant platform: three application services plus PostgreSQL, served through a single-origin gateway. This page explains how the pieces fit together, how the data is shaped, and how tenants stay isolated from one another.

## The services

The stack is four containers orchestrated by Docker Compose. Three of them are application code; the fourth is the database.

| Service | Path | Stack | Role |
| --- | --- | --- | --- |
| Backend | `apps/api/` | FastAPI (Python 3.12), SQLAlchemy, Alembic | REST API, auth, AI orchestration, knowledge retrieval |
| Frontend | `apps/web/` | Next.js (App Router), React, TypeScript, Tailwind | Dashboard, playground, client portal, web widget |
| WhatsApp bridge | `apps/whatsapp/` | Go over whatsmeow | Holds live WhatsApp sessions, relays messages |
| Database | — | PostgreSQL | Single source of truth for all state |

## The gateway

Everything is served from one origin by a Caddy gateway (`docker/Caddyfile`). It routes `/api/*` to the backend and everything else to the frontend:

```caddyfile
:80 {
	handle /api/* {
		reverse_proxy api:8000
	}
	handle {
		reverse_proxy web:3000
	}
}
```

Because the app is single-origin, the browser talks to a relative `/api` path and no CORS is needed for the normal flow. TLS is not bundled — put your own reverse proxy in front of the gateway port. See [Self-hosting](self-hosting.md) for the production setup.

## The data model

Every record hangs off an agency. The hierarchy, as defined in `apps/api/app/models.py`:

```text
Agency
├── User            (agency staff, login accounts)
├── ProviderCredential  (one encrypted AI key per provider)
└── Client
    ├── Agent
    │   ├── KnowledgeDocument → KnowledgeChunk
    │   ├── AgentQA           (question/answer pairs)
    │   └── Conversation → Message
    └── WhatsAppChannel  (one per client, bound to an agent)
```

A `Conversation` records its `channel` (playground, widget or WhatsApp) and a `mode` (`ai` or `human`); switching to `human` pauses the AI so an operator can answer from the inbox. Messages store their role, content and any knowledge `sources` used. See [Agents](agents.md) for how an agent's instructions, brief and knowledge compose into the prompt.

## Tenant isolation

The agency is the tenant boundary. `Agency`, `User`, `Client`, `Agent`, `WhatsAppChannel`, `Conversation` and other tables all carry an indexed `agency_id`, and every authenticated router query filters by the caller's `agency_id`. Deleting an agency cascades to everything it owns. Any new endpoint must preserve this filter.

## Encryption at rest

Sensitive values never hit the database in plaintext. AI provider API keys (`ProviderCredential.encrypted_api_key`) and the WhatsApp session marker and QR (`WhatsAppChannel.encrypted_auth_state`, `encrypted_qr`) are encrypted with Fernet, using a key derived from `ENCRYPTION_KEY` (`apps/api/app/security.py`). This value must never change once secrets are stored, or they can no longer be decrypted. Passwords are hashed with bcrypt. See [Configuration](configuration.md).

## Runtime behavior

- **Migrations on start** — the backend runs `alembic upgrade head` before accepting traffic, so the schema is always current. Schema changes require a new Alembic migration.
- **Stateful bridge** — the WhatsApp bridge (`apps/whatsapp/manager.go`) keeps live whatsmeow clients in memory; the session keys live in whatsmeow's own SQL store (`WHATSAPP_STORE_URL`) and the backend keeps a small encrypted marker per channel, so enabled sessions reconnect on startup. Backend and bridge authenticate to each other with `WHATSAPP_BRIDGE_TOKEN`. See [WhatsApp](whatsapp.md).
- **Rate limiting** — public, unauthenticated endpoints are throttled per IP by an in-memory limiter (`apps/api/app/ratelimit.py`), keyed on the client address from `X-Forwarded-For`.
