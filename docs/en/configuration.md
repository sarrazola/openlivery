# Configuration

> Leer en español: [configuration.md](../es/configuration.md)

OpenLivery is configured through environment variables. In Docker, they all live in a single `.env.docker` file at the repository root; a helper script generates it with strong random secrets so you never have to invent them yourself.

## The .env.docker file

Run the generator once per clone:

```bash
./scripts/generate-docker-env.sh   # writes .env.docker, refuses to overwrite an existing one
```

It creates the file with restrictive permissions (`umask 077`) and fills the sensitive values with `openssl rand`: a Postgres password, `SECRET_KEY`, `ENCRYPTION_KEY` and `WHATSAPP_BRIDGE_TOKEN`. Compose reads this file (`docker compose --env-file .env.docker`, which `make` does for you). The file is gitignored — keep it out of version control and back it up somewhere safe.

For a non-Docker local setup, the same variables go in a `.env` at the repo root or in `apps/api/.env`; see `.env.example`.

## Key variables

| Variable | Purpose | Default |
| --- | --- | --- |
| `DATABASE_URL` | SQLAlchemy connection string. In Docker it is assembled from `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` pointing at the `db` service | local Postgres |
| `SECRET_KEY` | Signs the JWT session tokens. Rotating it logs everyone out | dev placeholder |
| `ENCRYPTION_KEY` | Encrypts AI API keys and WhatsApp session state before they hit the database | dev placeholder |
| `ACCESS_TOKEN_MINUTES` | Session lifetime | `10080` (7 days) |
| `COOKIE_SECURE` | Send the session cookie only over HTTPS. Set `true` in production | `false` |
| `COOKIE_SAMESITE` | Cookie SameSite policy. Use `none` when the frontend and API are on different sites (requires `COOKIE_SECURE=true`) | `lax` |
| `RATE_LIMIT_ENABLED` | Per-IP rate limiting on public endpoints (auth, portal login, widget) | `true` |
| `FRONTEND_URL` | Origin allowed by CORS | `http://localhost:3000` |
| `WHATSAPP_BRIDGE_TOKEN` | Shared secret authenticating backend ↔ WhatsApp bridge calls. Use the same value on both | random |
| `NEXT_PUBLIC_API_URL` | Public API origin baked into the frontend at build time. Leave empty to use the same origin via the gateway | empty |
| `BACKEND_INTERNAL_URL` | How the web container reaches the API server-side (used by `proxy.ts` for custom portal domains) | `http://api:8000` |

### The ENCRYPTION_KEY warning

`ENCRYPTION_KEY` must **never** change once secrets have been stored. It derives the key that decrypts every saved AI API key and WhatsApp session. If you rotate or lose it, those secrets become unrecoverable — you will have to re-enter API keys and re-link WhatsApp numbers. Treat it as permanent for the lifetime of your database.

## Host ports

Compose binds each service to a host port, all overridable. Pass them inline to `make up`:

```bash
API_PORT=8001 WEB_PORT=3001 DB_PORT=5433 make up
```

| Variable | What it controls | Default |
| --- | --- | --- |
| `WEB_PORT` | The gateway port — this is the app | `3000` |
| `API_PORT` | Backend, exposed locally for OpenAPI docs and tooling | `8000` |
| `DB_PORT` | PostgreSQL | `5432` |
| `BIND_HOST` | Interface to bind to: `127.0.0.1` for local only, `0.0.0.0` to expose on a server | `127.0.0.1` |

The WhatsApp bridge listens on `3101` but is not published to the host in Docker.

## The single-origin gateway

A Caddy container (`docker/Caddyfile`) fronts the whole stack on one origin. It routes `/api/*` to the backend and everything else to the frontend, so the browser talks to a single port and `NEXT_PUBLIC_API_URL` can stay empty. The stack serves plain HTTP only — put your own reverse proxy in front of the gateway for TLS in production. See [Self-hosting](self-hosting.md) for a public deployment.
