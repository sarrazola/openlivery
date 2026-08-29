# Contributing

> Leer en español: [contributing.md](../es/contributing.md)

Docker is the fastest way to run OpenLivery, but for day-to-day development you usually want each service running on the host with hot reload. This guide covers running the backend, frontend and WhatsApp bridge locally, the test suites, migrations and the project conventions.

## Prerequisites

Clone the repository and enable the pre-commit guard once per clone:

```bash
git clone https://github.com/sarrazola/openlivery.git
cd openlivery
git config core.hooksPath .githooks
```

The guard (`.githooks/pre-commit`) blocks committing local-only files and any staged content flagged as internal. You need Python 3.12, Node.js, and a running PostgreSQL instance the backend can connect to.

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
npm install
npm run dev                     # tsx watch, listens on :3101
```

Run `npm test` for the test suite and `npm run build` to typecheck with `tsc`.

## Tests

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

## Conventions

All code, identifiers, comments, commit messages and docs are written in **English**, always. The only thing localized is the end-user UI, through the typed i18n system in `apps/web/lib/i18n` (English default, Spanish for now). Never introduce non-English in code or docs — put user-facing copy behind i18n keys instead.

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
| WhatsApp | `npm run dev` | Run the bridge on :3101 |
| WhatsApp | `npm test` | Run the test suite |
| WhatsApp | `npm run build` | Typecheck with tsc |

## Next steps

- [Architecture](architecture.md) — how the services fit together.
- [Configuration](configuration.md) — environment variables, secrets and ports.
- [Self-hosting](self-hosting.md) — deploy to a public server with TLS and backups.
