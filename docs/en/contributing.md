# Contributing

> Leer en español: [contributing.md](../es/contributing.md)

Docker is the fastest way to run OpenLivery, but for day-to-day development you usually want each service running on the host with hot reload. This guide covers running the backend, frontend and WhatsApp bridge locally, the test suites, migrations and the project conventions.

## Installation scope

Each installation serves one agency with multiple client workspaces. First-run
setup creates that agency and its owner, then public registration closes. Do not
add configuration, API routes, or UI flows for registering additional agencies.
Keep ownership checks and existing data intact when changing setup or login.

## Prerequisites

Clone the repository and enable the pre-commit guard once per clone:

```bash
git clone https://github.com/sarrazola/openlivery.git
cd openlivery
git config core.hooksPath .githooks
```

The guard (`.githooks/pre-commit`) blocks committing local-only files and any staged content flagged as internal. You need Python 3.12, Node.js, Go 1.27+, and a running PostgreSQL instance the backend can connect to.

## Backend (apps/api)

Copy `.env.example` to `.env` and point `DATABASE_URL` at your PostgreSQL. Install dependencies, apply migrations, then start the server with reload:

```bash
cd apps/api
pip install -r requirements.txt
alembic upgrade head            # migrations must run before starting
uvicorn app.main:app --reload --port 8000
```

OpenAPI docs are served at [http://localhost:8000/docs](http://localhost:8000/docs).

## Frontend (apps/web)

```bash
cd apps/web
npm install
npm run dev                     # http://localhost:3000
```

Use `npm run lint` before committing and `npm run build` to verify a production build. Note that this is Next.js 16 (App Router) — check the docs bundled under `node_modules/next/dist/docs/` before writing non-trivial Next.js code, as several APIs differ from earlier versions.

## WhatsApp bridge (apps/whatsapp)

```bash
cd apps/whatsapp
go run .                        # listens on :3101
```

The bridge is a single Go binary (Go 1.27+); there is no install step. Run `go test ./...` for the test suite and `go vet ./...` to check the build.

## Tests

All changes to `main`, including documentation, go through a pull request.
The required GitHub Actions checks are `api`, `web`, and `whatsapp` from the
`Tests` workflow. Wait for all three to pass before merging. Direct pushes to
`main` are blocked, including for repository administrators.

If a check fails, read its log in the pull request's **Checks** tab and push the
fix to the same branch; the workflow runs again automatically. Workflows for
external contributors require maintainer approval before they run.

The backend tests need a **separate** database — never point them at your dev DB. They default to `openlivery_test` on localhost and create/drop all tables per test. Override the target with `TEST_DATABASE_URL`:

```bash
cd apps/api
pytest -q
TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/openlivery_test pytest -q
```

Run a single test by node id:

```bash
pytest tests/test_flows.py::test_register_login_logout_and_me -v
```

## Database migrations

Any schema change requires a new Alembic migration — Docker runs `alembic upgrade head` on backend start, so a change without a migration will break the containerized stack. Generate one after editing the models, review the generated file, then apply it.

A migration runs on installs that already hold data and are serving traffic, so a few rules apply, each enforced by `apps/api/tests/test_migration_conventions.py`:

- **One file per revision, named after it, and a single head.** If `main` gained a migration while you worked, rebase yours onto it. Watch for stray copies of a file in `migrations/versions/`.
- **A revision id of 32 characters at most.** That is what Alembic's version table stores.
- **No schema names.** Leave tables unqualified and do not set `search_path` or create extensions; a migration runs under the `search_path` its deployment gives it.
- **A `downgrade()` that works.** It is the way back when a release is reverted.
- **`conversations` before the channel tables.** A reply locks them in that order, and a migration that takes them the other way round deadlocks against live traffic.
- **Removing data is a written decision.** Dropping a table or column, changing a column type or deleting rows needs a `# contract: reviewed` line saying why the previous release keeps working, or what the operator must do first. Prefer removing in a later release than the one that stops reading it.
- **A merged migration is never edited.** Installs that ran it will not run it again; add a new revision.

Every pull request runs the `Tests` workflow: the API suite, the migrations applied to an empty database and the newest ones reverted and applied again, the web lint and build, and the bridge's `go vet` and `go test`.

## Conventions

All code, identifiers, comments, commit messages and docs are written in **English**, always. The only thing localized is the end-user UI, through the typed i18n system in `apps/web/lib/i18n` (English default, Spanish for now). Never introduce non-English in code or docs — put user-facing copy behind i18n keys instead.

## Extension points

A deployment that runs OpenLivery for others may need to add to it without
forking. These are the places that are meant for that, kept stable on purpose;
changing their shape is a breaking change and gets a line in the changelog:

- `app.database.get_db` (a FastAPI dependency) and `new_session()`: the one
  place sessions come from, so a substituted session reaches every query.
- `app.services.providers.register_credential_fallback(fn, available=probe)`:
  lends a key to an agency that stored none; `credential_source()` says which
  one would answer, and `GET /api/providers` reports it as `source`.
- `app.services.usage.register_usage_hook(fn)`: sees every usage record as it
  is written, inside the caller's session; it cannot fail the reply.
- `app.services.notifications.register_provider(name, fn)`: delivers push
  notifications; `PUSH_PROVIDER` selects one.
- `apps/web/lib/extensions/agent-tools.tsx`: keeps deployment-managed tools out
  of the agent editor's custom list and renders a section under it. Replaced at
  build time.
- `NEXT_PUBLIC_EXTRA_NAV`, `NEXT_PUBLIC_PUBLIC_PATHS`, `NEXT_PUBLIC_COMMUNITY_LINKS`:
  build-time hooks of the web shell.

## Command reference

| Service | Command | What it does |
| --- | --- | --- |
| Backend | `pip install -r requirements.txt` | Install Python dependencies |
| Backend | `alembic upgrade head` | Apply pending migrations |
| Backend | `uvicorn app.main:app --reload --port 8000` | Run the API with hot reload |
| Backend | `pytest -q` | Run the test suite |
| Frontend | `npm install` | Install dependencies |
| Frontend | `npm run dev` | Run the dev server on :3000 |
| Frontend | `npm run lint` | Lint with ESLint |
| Frontend | `npm run build` | Production build |
| WhatsApp | `go run .` | Run the bridge on :3101 |
| WhatsApp | `go test ./...` | Run the test suite |
| WhatsApp | `go vet ./...` | Check the build |

## Next steps

- [Architecture](architecture.md) — how the services fit together.
- [Configuration](configuration.md) — environment variables, secrets and ports.
- [Self-hosting](self-hosting.md) — deploy to a public server with TLS and backups.
