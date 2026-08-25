# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

OpenLivery is a multi-tenant platform where agencies create and manage AI agents for their clients, with a chat playground, a client portal, and WhatsApp integration. Three services + PostgreSQL:

- `apps/api/` — FastAPI (Python 3.12) + SQLAlchemy + Alembic
- `apps/web/` — Next.js 16 (App Router) + React 19 + TypeScript + Tailwind
- `apps/whatsapp/` — Node.js bridge over Baileys (WhatsApp Web protocol)

**Language convention (always follow):** all code — routes, identifiers, comments, commit messages, and docs — is written in English, always. The only thing that is localized is the end-user UI, through a typed i18n system (`apps/web/lib/i18n`): English (default) and Spanish for now. Never introduce non-English in code or docs; put user-facing copy behind i18n keys instead. (The system prompt sent to the LLM in `apps/api/app/services/knowledge.py` is a deliberate exception, kept in the customer's language.)

## Repo hygiene

Enable the pre-commit guard once per clone: `git config core.hooksPath .githooks`. It blocks committing local-only files (`work/`, `internal/`, `*.local.md`) and any staged content matching terms in `work/forbidden-words.txt` (gitignored) or a `DO-NOT-COMMIT` marker. Keep internal notes/roadmap in `work/` (gitignored) — never in the repo.

## Commands

### Docker (recommended)

A `Makefile` wraps compose: `make up` builds and starts everything; also `make down/logs/migrate/test/help`. Override host ports inline to avoid clashes: `API_PORT=8001 WEB_PORT=3001 make up` (`API_PORT`/`WEB_PORT`/`DB_PORT`/`BIND_HOST`).

```bash
./scripts/generate-docker-env.sh                       # create .env.docker with random secrets
docker compose --env-file .env.docker up --build -d
docker compose --env-file .env.docker logs -f api  # or: web, whatsapp, db
docker compose --env-file .env.docker exec api pytest -q
```

### Local

```bash
# Backend (needs PostgreSQL and a .env, see .env.example)
cd apps/api
pip install -r requirements.txt
alembic upgrade head                 # migrations must run before starting
uvicorn app.main:app --reload --port 8000

# Frontend
cd apps/web && npm install && npm run dev    # http://localhost:3000
npm run lint                                 # eslint
npm run build

# WhatsApp bridge
cd apps/whatsapp && npm install && npm run dev    # tsx watch, listens on :3101
npm test                                     # node test runner via tsx
npm run build                                # tsc typecheck
```

### Backend tests

Tests need a separate `openlivery_test` database (default URL in `apps/api/tests/conftest.py`, override with `TEST_DATABASE_URL`). Tables are created/dropped per test — never point it at the dev DB.

```bash
cd apps/api
pytest -q
pytest tests/test_flows.py::test_register_login_logout_and_me -v   # single test
```

## Architecture

### Data model (apps/api/app/models.py)

Everything is agency-scoped: `Agency → Users, Clients, AIConnections`; `Client → Agents, WhatsAppChannel, Conversations`; `Agent → Conversations, KnowledgeDocuments`; `Conversation → Messages`. Every router query filters by the authenticated user's `agency_id` — preserve this in any new endpoint; it's the tenant-isolation boundary.

### Backend layout

- `app/main.py` — app creation, CORS, router registration
- `app/routers/` — one file per domain (auth, agency, clients, agents, connections, conversations, dashboard, portal, whatsapp); `domains.py` holds the public, unauthenticated `/api/public/portal-domain` used by the frontend `proxy.ts` and the gateway's on-demand-TLS `ask` hook to map a client's custom domain to its portal
- `app/services/ai.py` — `chat_completion()` calls any OpenAI-compatible endpoint (base_url + model are per-connection config); connection testing lists `{base_url}/models`
- `app/services/knowledge.py` — PDF text (pypdf on upload) is chunked and embedded; retrieval is semantic (cosine over embeddings stored as JSON) with keyword ranking as a fallback, then assembled into the system prompt
- `app/security.py` — JWT in httpOnly cookies; AI API keys and WhatsApp session state are encrypted with a key derived from `ENCRYPTION_KEY` before hitting the DB
- `app/ratelimit.py` — per-IP in-memory limiter used as a route dependency on public/unauthenticated endpoints (auth + portal login, widget messages); reads the client from `X-Forwarded-For` (set by the gateway); toggle with `RATE_LIMIT_ENABLED` (disabled in tests)
- `migrations/` — Alembic; schema changes require a new migration, and Docker runs `alembic upgrade head` on backend start

### WhatsApp flow

The bridge (`apps/whatsapp/src/manager.ts`) holds live Baileys sessions and is stateful — encrypted session/auth state lives in PostgreSQL (via the backend), and the bridge reloads enabled sessions on startup. Incoming messages: bridge → `POST /api/whatsapp/channels/{channel_id}/inbound` on the backend → AI reply sent back through the bridge. Backend↔bridge calls authenticate with `WHATSAPP_BRIDGE_TOKEN`. Conversations have a `mode` field: switching to `"human"` pauses the AI so an operator answers from the portal.

### Frontend

`apps/web/lib/api.ts` is the single fetch wrapper (cookie auth, `NEXT_PUBLIC_API_URL`); `apps/web/lib/providers.ts` holds per-provider model presets. `apps/web/CLAUDE.md` → `AGENTS.md` warns that Next.js 16 has breaking changes vs. training data — check `node_modules/next/dist/docs/` before writing non-trivial Next.js code.

## Environment gotchas

- `ENCRYPTION_KEY` must never change after secrets are stored — it decrypts AI API keys and WhatsApp sessions.
- The app is served single-origin through a Caddy gateway (`docker/Caddyfile`): `/api/*` → backend, everything else → frontend. The browser uses relative `/api` (`lib/api.ts` falls back to `""`), so `NEXT_PUBLIC_API_URL` is empty by default and only set to point the frontend at an API on a separate origin (baked at build time — rebuild the web image to change it).
- TLS is operator-provided: put your own reverse proxy in front of the gateway port; the stack itself only serves plain HTTP. No bundled TLS/`make deploy`.
- Custom per-client portal domains are opt-in: mount `docker/Caddyfile.ondemand` (on-demand TLS gated by `/api/public/portal-domain`) via a compose override; `apps/web/proxy.ts` (Next.js 16 renamed `middleware`→`proxy`) rewrites a verified custom host to `/portal/[slug]`. `BACKEND_INTERNAL_URL` lets the web container reach the API server-side.
- Ports: gateway `WEB_PORT` (default 3000, the app), backend 8000 (OpenAPI docs at `/docs`, exposed locally for tooling), bridge 3101 (not exposed in Docker).
