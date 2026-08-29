# Self-hosting OpenLivery

> Leer en español: [self-hosting.md](../es/self-hosting.md)

Run and operate your own OpenLivery instance. For a feature overview see the
[README](../README.md).

OpenLivery is orchestrated by Docker Compose, with a `Makefile` wrapping the
common commands. A lightweight **gateway** (Caddy) is the single public entry
point: it serves the app and routes `/api/*` to the backend, so the frontend and
API share one origin.

| Service | Image | Role |
| --- | --- | --- |
| `proxy` | Caddy | HTTP gateway — the app's single origin (routes `/api/*` → backend). |
| `web` | Next.js | Agency dashboard, client portal, playground, widget (internal). |
| `api` | FastAPI | REST API, models, AI/knowledge/provider services (internal). |
| `db` | PostgreSQL | All data (encrypted secrets at rest, internal). |
| `whatsapp` | Node.js + Baileys | WhatsApp Web bridge (internal). |

Only the gateway is meant to be public. For HTTPS, put your own reverse proxy in
front of it (see [Go to production](#go-to-production-https)). One instance =
**one agency** (the first registered user is its admin).

> **Why Caddy for the gateway?** The routing is deliberately simple — two
> upstreams and one rule (`/api/*` → backend, everything else → frontend) — and
> authentication lives in the API (JWT in an httpOnly cookie), not at the edge. A
> single small binary with a tiny config fits that; heavier programmable gateways
> (Envoy, Kong) earn their keep with many services and edge auth/key validation,
> which this stack does not need. The gateway is isolated to the `proxy` service,
> so swapping it later touches nothing else.

## Contents

- [Before you begin](#before-you-begin)
- [Install](#install)
- [Access your install](#access-your-install)
- [Secure your install](#secure-your-install)
- [Go to production (HTTPS)](#go-to-production-https)
- [Environment variables](#environment-variables)
- [Manage your install](#manage-your-install)
- [Persistent data](#persistent-data)
- [Backups](#backups)
- [Upgrade](#upgrade)
- [Uninstall](#uninstall)
- [Run without Docker](#run-without-docker)
- [Connect WhatsApp](#connect-whatsapp)
- [Tests](#tests)
- [WhatsApp / Baileys caveats](#whatsapp--baileys-caveats)
- [Troubleshooting](#troubleshooting)

## Before you begin

You need a host with Docker:

- macOS / Windows — [Docker Desktop](https://www.docker.com/products/docker-desktop/).
- Linux / a server — Docker Engine with the Compose plugin.

Check it is running:

```bash
docker --version
docker compose version
```

For a public deployment you also need a **domain** and a server with ports
**80** and **443** open (see [Go to production](#go-to-production-https)).

## Install

```bash
git clone <REPOSITORY_URL>
cd openlivery
./scripts/generate-docker-env.sh   # writes .env.docker with random secrets (gitignored)
make up                            # build, start, run migrations
```

`make up` builds the images, starts the containers, creates the database and
applies the Alembic migrations. Every service should report `healthy`:

```bash
make ps
```

Override host ports inline when they clash with other services:

```bash
API_PORT=8001 WEB_PORT=3001 DB_PORT=5433 make up
```

### Run from prebuilt images (no local build)

Tagged images are published to the GitHub Container Registry on every push to
`main`, so a server can skip building and pull them instead:

```bash
make pull        # docker compose pull + up -d
```

This pulls `ghcr.io/sarrazola/openlivery-{api,web,whatsapp}:latest`. Pin a release
with `OPENLIVERY_VERSION=v1.2.3 make pull`, or point at your own registry with
`OPENLIVERY_IMAGE_PREFIX`. The prebuilt `web` image calls the API through the
gateway with relative `/api`; to target an API on a separate origin you must
build the frontend yourself with `NEXT_PUBLIC_API_URL` set.

## Access your install

- **App / dashboard** — http://localhost:3000 (the gateway)
- **API docs** — http://localhost:8000/docs (the API is exposed locally for tooling)
- **PostgreSQL** — `make shell-db` (or connect to `localhost:5432`)

On the first screen choose **Create agency**; that account is the admin. Only the
gateway is meant to be reachable publicly; the web, API, database and WhatsApp
bridge stay on the private Compose network.

## Secure your install

Do this before exposing OpenLivery to anyone else.

- **Secrets.** `generate-docker-env.sh` fills `SECRET_KEY`, `ENCRYPTION_KEY`,
  `WHATSAPP_BRIDGE_TOKEN` and `POSTGRES_PASSWORD` with random values. If you set
  them by hand, use long random strings and never reuse them across installs.
- ⚠️ **`ENCRYPTION_KEY` must never change** once secrets are stored — it decrypts
  the provider API keys and the WhatsApp sessions. Losing or changing it makes
  them unrecoverable.
- **Keep services private.** Leave `BIND_HOST=127.0.0.1` (the default) so the
  database, API and frontend are only reachable from the host; expose the app to
  the internet **only** through the reverse proxy (next section). Never publish
  the PostgreSQL port on a public interface.
- **Do not commit `.env.docker`** or any backup that contains it; store it in a
  secret manager.
- Provider API keys are encrypted at rest and never returned in full to the
  browser; the WhatsApp auth state and QR are encrypted too. `WHATSAPP_BRIDGE_TOKEN`
  authenticates the backend↔bridge calls — do not reuse it as a password or key.
- **Rate limiting.** Public, unauthenticated endpoints are throttled per client
  IP: sign-in and sign-up (agency and portal) to blunt brute force, and the web
  widget's message endpoint because each call spends LLM tokens. Limits are
  in-memory (fine for one instance); set `RATE_LIMIT_ENABLED=false` if a proxy in
  front already enforces limits, or add proxy-level limits for a scaled setup. The
  limiter reads the client from `X-Forwarded-For`, which the gateway sets.

## Go to production (HTTPS)

The stack serves plain HTTP on the gateway. For a public deployment, put **your
own reverse proxy** (Caddy, nginx, Traefik, a cloud load balancer…) in front of
the gateway to terminate TLS with your domain — the usual self-hosting model.

1. Run the stack; the gateway listens on `${WEB_PORT}` (default `3000`), bound to
   `127.0.0.1`.
2. Point your reverse proxy at `127.0.0.1:${WEB_PORT}` and serve your domain over
   HTTPS. Because the app and API share one origin, proxy the **whole domain** to
   that single port — there is nothing else to route.
3. Set `COOKIE_SECURE=true` in `.env.docker` and restart, so the session cookie
   is only sent over TLS.

Example with Caddy (automatic HTTPS) running on the host:

```caddyfile
agency.example.com {
	reverse_proxy 127.0.0.1:3000
}
```

Keep the database, API and WhatsApp bridge private (`BIND_HOST=127.0.0.1`, the
default); only your reverse proxy should face the internet.

## Custom domains for client portals

By default a client's portal lives at `your-domain/portal/<slug>`. You can also
serve it under the **client's own domain** (e.g. `chat.brand.com`) for a fully
white-label experience. This is opt-in because it requires the gateway to
terminate TLS and obtain certificates on demand.

**1. Enable the multi-domain gateway.** Create a `docker-compose.override.yml`
next to `docker-compose.yml` (Compose merges it automatically):

```yaml
services:
  proxy:
    volumes:
      - ./docker/Caddyfile.ondemand:/etc/caddy/Caddyfile:ro
      - caddy_data:/data          # persist issued certificates across restarts
    environment:
      PRIMARY_DOMAIN: app.youragency.com   # your main domain
    ports:
      - "80:80"
      - "443:443"

volumes:
  caddy_data:
```

Point `app.youragency.com` (and every client domain) at this server, then
`make up`. The gateway obtains a certificate for the primary domain normally, and
for each client domain **on demand** — but only after asking the API whether that
domain is a verified portal domain (`/api/public/portal-domain`), so it never
issues certificates for arbitrary hosts aimed at your IP.

**2. Add the domain for a client.** In the dashboard open the client → **Portal**
tab → **Custom domain**, enter the domain and save. Create the two DNS records it
shows:

| Type | Host | Value |
| --- | --- | --- |
| `CNAME` | `chat.brand.com` | your gateway host (e.g. `app.youragency.com`) |
| `TXT` | `_openlivery-challenge.chat.brand.com` | the token shown |

Click **Verify**. Once the TXT record is found the domain is marked verified, the
gateway starts issuing its certificate, and the frontend routes the domain to
that client's portal. The portal must be **published** for the domain to serve.

> Without the override the app stays single-origin behind your own reverse proxy,
> and portals are reachable only at `/portal/<slug>`.

## Environment variables

`generate-docker-env.sh` fills the secrets. To set values by hand, copy
`.env.docker.example` to `.env.docker` and replace every `CHANGE_*`.

| Variable | Scope | Use |
| --- | --- | --- |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Private network | Main PostgreSQL database. |
| `POSTGRES_TEST_DB` | Private network | Isolated database for `pytest`. |
| `SECRET_KEY` | Backend | Signs the agency and portal sessions. |
| `ENCRYPTION_KEY` | Backend / persisted data | Encrypts API keys, QR and the WhatsApp session. **Must not change** after secrets are stored. |
| `WHATSAPP_BRIDGE_TOKEN` | Backend + bridge | Authenticates the private backend↔bridge calls. |
| `FRONTEND_URL` | Backend | Origin allowed by CORS (only needed if you serve the API on a separate origin). |
| `NEXT_PUBLIC_API_URL` | Browser / frontend build | Leave empty (default): the browser calls the API through the gateway with relative `/api`. Set it only to point the frontend at an API on a separate origin (baked at build time). |
| `COOKIE_SECURE` | Backend | `true` behind HTTPS so the session cookie is only sent over TLS. |
| `COOKIE_SAMESITE` | Backend | `lax` (default); `none` when the frontend and API are on different sites (requires `COOKIE_SECURE=true`). |
| `ACCESS_TOKEN_MINUTES` | Backend | Session lifetime. |
| `WHATSAPP_LOG_LEVEL` | Bridge | Log level; `silent` avoids exposing sensitive data. |
| `API_PORT`, `WEB_PORT`, `DB_PORT` | Host | Host ports (defaults `8000` / `3000` / `5432`). |
| `BIND_HOST` | Host | Bind address: `127.0.0.1` (local) or `0.0.0.0` (expose directly). |

## Manage your install

```bash
make logs                 # follow logs from all services (SERVICE=api to filter)
make ps                   # service status
make stop                 # stop containers (keep them)
make start                # start stopped containers
make restart              # restart all services
make migrate              # apply Alembic migrations in the running api container
make shell-api            # shell inside the api container
make shell-db             # psql inside the database
make down                 # stop and remove containers (keeps data volumes)
```

Run `make help` for the full list.

## Persistent data

All state lives in named Docker volumes, so `make down` and upgrades keep it:

| Volume | Contents |
| --- | --- |
| `postgres_data` | The PostgreSQL database — agencies, agents, conversations, encrypted provider keys and encrypted WhatsApp session state. |
| `backend_storage` | Uploaded files (e.g. knowledge-base PDFs). |

The `ENCRYPTION_KEY` decrypts the provider API keys and WhatsApp sessions.
**Never change it** once secrets are stored, or they become unrecoverable —
treat it as part of your backup.

## Backups

Export PostgreSQL without stopping the app:

```bash
mkdir -p backups
docker compose --env-file .env.docker exec -T db \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > backups/openlivery.dump
```

Also store `.env.docker` in a secret manager: a backup with API keys or a
WhatsApp session needs the same `ENCRYPTION_KEY` to be decrypted.

Restore (replaces data in the target database — back up first):

```bash
docker compose --env-file .env.docker stop api whatsapp
docker compose --env-file .env.docker exec -T db \
  sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' < backups/openlivery.dump
docker compose --env-file .env.docker start api whatsapp
```

## Upgrade

```bash
git pull
make up        # rebuilds and restarts; your reverse proxy stays in front
```

New images are built and the backend runs `alembic upgrade head` on start, so
schema changes are applied automatically. Take a backup first.

## Uninstall

`make down` removes the containers and network but keeps your data. To delete
**everything** — database, PDFs, keys and WhatsApp sessions in the volumes:

```bash
make destroy   # irreversible
```

## Run without Docker

Requirements: Python 3.12+, Node.js 20+, PostgreSQL 14+ running.

```bash
# 1) databases
psql -d postgres -c "CREATE ROLE openlivery LOGIN PASSWORD 'openlivery';"
createdb -O openlivery openlivery
createdb -O openlivery openlivery_test

# 2) env
cp .env.example .env          # then set SECRET_KEY and ENCRYPTION_KEY

# 3) backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r apps/api/requirements.txt
cd apps/api && alembic upgrade head && uvicorn app.main:app --reload --port 8000

# 4) frontend (new terminal)
cd apps/web && npm install && npm run dev

# 5) WhatsApp bridge (new terminal)
cd apps/whatsapp && npm install && npm run start
```

The bridge listens only on `127.0.0.1:3101` and must stay running alongside the
backend. See `.env.example` for the full variable list (`DATABASE_URL`,
`BACKEND_URL`, `WHATSAPP_BRIDGE_URL`, `WHATSAPP_BRIDGE_PORT`, …).

## Connect WhatsApp

1. Open **Clients → the client → Channels → WhatsApp → Configure**.
2. Choose one of that client's agents and click **Connect with QR code**.
3. On the phone: **WhatsApp → Settings → Linked devices → Link a device**, scan
   the QR and wait for **Connected**.

Incoming messages appear in the agency **Inbox** and the client portal. Click
**Take over** to answer as a human (the AI pauses) and **Return to AI** to
resume. On restart the bridge reloads enabled sessions from PostgreSQL and
reconnects automatically — no new QR unless WhatsApp ends the session, the device
is unlinked or `ENCRYPTION_KEY` changes.

## Tests

Inside Docker:

```bash
make test   # backend pytest + rebuild the web/whatsapp validation stages
```

Locally:

```bash
cd apps/api && ../../.venv/bin/pytest -q     # backend (needs the openlivery_test DB)
cd apps/whatsapp && npm test && npm run build
cd apps/web && npm run lint && npm run build
```

Re-test the migrations from scratch:

```bash
cd apps/api && alembic downgrade base && alembic upgrade head
```

## WhatsApp / Baileys caveats

Baileys connects to the multi-device protocol of **WhatsApp Web**; the number is
linked as an extra device via QR. It is **not** the official WhatsApp Business
Cloud API, and this project is not affiliated with or endorsed by WhatsApp/Meta.

- WhatsApp may change its protocol or revoke a session/device without notice.
- Abusive automation, spam or mass sending can get a number restricted. Use only
  numbers authorized by each client and respect WhatsApp's terms.
- The QR links the account while valid — never share it or screenshot it publicly.
- The integration handles one-to-one conversations (text, plus transcribed voice
  notes and described images when the agent's capabilities are on). It ignores
  groups, statuses, newsletters, documents, locations, reactions and calls.
- One WhatsApp account belongs to one client; another client needs a different
  number. `apps/whatsapp/package.json` pins an exact Baileys version.

## Troubleshooting

- **Ports already in use.** Override them inline:
  `API_PORT=8001 WEB_PORT=3001 DB_PORT=5433 make up`.
- **A service is unhealthy.** Check its logs with `make logs SERVICE=api` (or
  `web`, `whatsapp`, `db`) and `make ps` for status.
- **Session does not persist, or login loops behind HTTPS.** Make sure
  `COOKIE_SECURE=true` is set and you are reaching the app over TLS.
- **Provider keys or the WhatsApp session stopped decrypting.** The
  `ENCRYPTION_KEY` changed — restore the original value from your backup.
- **WhatsApp asks for a new QR after a restart.** Normal only if WhatsApp ended
  the session, the device was unlinked or `ENCRYPTION_KEY` changed; otherwise
  the bridge reloads enabled sessions from PostgreSQL automatically.
