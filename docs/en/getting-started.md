# Getting started

> Leer en español: [getting-started.md](../es/getting-started.md)

OpenLivery runs as three services plus PostgreSQL, orchestrated by Docker Compose. The fastest way to try it is to clone the repository, generate secrets and bring the stack up with a single command.

## Requirements

You need the following tools on the host:

- [Docker](https://docs.docker.com/get-docker/) — Docker Desktop, or Docker Engine with the Compose plugin.
- Git, GNU Make, a POSIX-compatible shell and OpenSSL.

The commands in this guide are written for a POSIX-compatible shell. On Windows,
run them from WSL or Git Bash rather than PowerShell. Python, Node.js, Go and
PostgreSQL run inside the containers and do not need to be installed on the host
for this setup.

Check the prerequisites before continuing:

```bash
git --version
docker --version
docker compose version
make --version
sh -c 'echo POSIX shell: $0'
openssl version
```

## Install and run

```bash
git clone https://github.com/sarrazola/openlivery.git
cd openlivery
./scripts/generate-docker-env.sh   # writes .env.docker with random secrets (gitignored)
make up                            # build images, start services, run migrations
```

`make up` wraps Docker Compose: it builds the images, starts the four services and applies the database migrations before the API accepts traffic.

## Open the app

Once the stack is healthy:

- **App** — [http://localhost:3000](http://localhost:3000)
- **API docs (OpenAPI)** — [http://localhost:8000/docs](http://localhost:8000/docs)

If those ports are already in use, override them inline:

```bash
API_PORT=8001 WEB_PORT=3001 DB_PORT=5433 make up
```

Prefer not to build locally? `make pull` runs the prebuilt images published to GHCR instead of building from source.

## First steps

1. **Create your agency** on the first screen — this is the top-level workspace that owns everything else.
2. Open **Settings** and add an OpenAI and/or Anthropic API key. The key is verified when you save it. See [AI providers](ai-providers.md).
3. Create a **client**, then an **agent** for that client: pick a provider and model and write the agent's instructions. See [Agents](agents.md).
4. Add knowledge (context, Q&A pairs, PDFs) and optionally enable image or audio understanding. See [Knowledge base](knowledge-base.md).
5. Open the **Playground** to chat with the agent, then connect a [WhatsApp](whatsapp.md) number or embed the [web widget](web-widget.md).

## Useful commands

| Command | What it does |
| --- | --- |
| `make up` | Build, start and migrate the whole stack |
| `make down` | Stop and remove the containers |
| `make logs` | Follow logs from all services |
| `make migrate` | Apply pending database migrations |
| `make test` | Run the backend test suite |
| `make help` | List every available target |

## Next steps

- [Configuration](configuration.md) — environment variables, secrets and ports.
- [Architecture](architecture.md) — how the services fit together.
- [Self-hosting](self-hosting.md) — deploy to a public server with TLS and backups.

## Switching a client off, or deleting it

**Active client** off stops everything without losing anything: its agents stop answering on every channel, the web chat is hidden and the portal closes. Switch it back on and the service resumes.

**Delete client** removes the client and everything under it: agents with their knowledge and tools, channels, contacts, conversations with all their messages, and the people with portal access. The dialog shows those counts (`GET /api/clients/{id}/deletion-preview`) and asks for the client's name before the button works. A linked WhatsApp device is logged out first.
