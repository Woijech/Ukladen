# Ukladen

Ukladen is a personal workspace for a university schedule, personal calendar,
notes and study materials. Academic selection is optional: personal events and
pages work without a subject or university group. Official IIS facts stay separate
from the user's changes.

The product is under active development. The browser provides account registration/login, optional BSUIR group selection,
a day/week calendar, notes, materials, databases, collections/tags, search,
reminders/inbox and profile settings in a shared light/dark interface. See the
[frontend guide](docs/architecture/frontend.md) for current UI limits.

## Current capabilities

| Area | Status |
| --- | --- |
| Email/password and Google authentication, account linking, verification and recovery | Implemented backend and browser UI; verified email and a password are required for workspace access |
| User profile/avatar, academic profile and public IIS directories | Implemented backend/UI for profile/avatar and group selection |
| Official schedule synchronization, personal events, official overrides and resolved calendar | Implemented backend; UI supports day/week reads and personal-event create/edit/delete; official override editing remains API-only |
| Independent nested pages, typed blocks, Markdown compatibility and recoverable trash | Implemented backend/UI for flat blocks, hierarchy and trash |
| Page/calendar/material links, collections, tags and saved calendar views | Implemented backend; UI for page/event/material links and collections/tags; saved event views remain API-only |
| User databases, typed properties, page-backed records, table/calendar views and date moves | Implemented backend; UI for schemas, records, saved table/day/week/month views and form date edits; mixed display and drag moves remain API-only |
| One-shot calendar reminders and in-app notifications | Implemented backend/UI for one-shot calendar reminders, pending cancellation and inbox |
| Private materials, bounded document extraction and PostgreSQL full-text search | Implemented backend/UI for files/bookmarks, processing status and filtered full-text search |
| Offline AI chat/run lifecycle | Implemented fake-only backend with accounting, checkpoints, bounded recovery and 30-day cleanup; disabled by default, migrations unapplied to the app; see [AI setup](docs/development/ai-setup.md) |
| Tasks, free slots/conflicts, semantic search, real AI and RAG | Planned; runtime not implemented |
| Collaboration, formulas and private IIS accounts/grades | Deferred; private API contracts unverified |

The [product specification](docs/product/overview.md) and
[implementation roadmap](docs/development/implementation-roadmap.md) maintain the
full status. A package marker or installed pgvector extension is not a feature.

## Architecture and stack

One **modular monolith** serves HTTP and background jobs. API, ordinary worker,
material worker and Beat share the same Python backend and PostgreSQL data model.

```text
Browser → Next.js / Traefik → FastAPI → PostgreSQL 18 + pgvector
                                  ├→ Redis → Celery workers / Beat
                                  └→ SeaweedFS (private S3 objects)
```

- Backend: Python 3.14, FastAPI, Pydantic Settings, SQLAlchemy, Psycopg, Alembic.
- Frontend: Next.js 16, React 19, TypeScript, TanStack Query; React/CSS calendar.
- Services: PostgreSQL 18, Redis 7.4, Celery, SeaweedFS, Traefik.
- Quality: uv/lockfile, Ruff, Pyright, pytest, npm/lockfile, ESLint, Playwright, GitHub Actions.

Application services own business rules. Dependencies follow
`presentation → application → domain`; infrastructure implements ports. Binary
files stay in S3, PostgreSQL owns canonical data, and Redis is disposable.
See [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) for the architecture contract
and [AGENTS.md](AGENTS.md) for development rules.

```text
apps/backend/     API, business modules, integrations, workers, Alembic and tests
apps/web/         Next.js App Router frontend and browser tests
infra/            Traefik routes and home Compose validation
docs/             Product contracts, architecture, ADRs, development and deployment
assets/branding/  Approved A1 logo source exports (frontend copies are intentional)
docker-compose.yml       Local development stack
docker-compose.home.yml  Optional home-hosting overlay
.env.example             Local configuration example
.env.home.example        Home configuration template; mandatory secrets are blank
```

## Requirements

Docker Engine and Compose v2 are enough for the full local stack. The home overlay
requires Compose **2.24.4 or newer**. Host development additionally uses **uv 0.11.11**,
**Python 3.14**, **Node.js 22** and npm. Initial installs/builds need network access.
The default local ports are 8080, 3000, 8000, 5432, 6379, 8333 and 23646.

## First local start

From the repository root, create configuration only if it does not already exist:

```bash
test -f .env || cp .env.example .env
docker compose config --quiet
docker compose up --build --detach --wait --wait-timeout 180
```

Open [Ukladen](http://localhost:8080) or [API docs](http://localhost:8080/api/docs).
The `migrate` service applies Alembic before API startup. All base Compose ports
bind to localhost. `docker compose down` stops containers and preserves data volumes.

**Configure email before expecting registration to complete.** The local example
uses `AUTH_EMAIL_DELIVERY_MODE=fake`, which sends no mail and keeps tokens only in
worker memory. Set `smtp` and your provider's host, verified sender and credentials
for usable verification/recovery links; follow [email setup](docs/development/auth-email.md).
Google login is optional and needs its own Web application OAuth client.

The [ENV reference](docs/development/environment.md) explains every backend setting,
required values, defaults, empty-value behavior, container overrides, Google/SMTP
setup and isolated test variables. Never overwrite an existing `.env` or `.env.home`
with an example, and never commit or share real credentials.

## Run the applications on the host

Start supporting services from the root, then run the backend:

```bash
docker compose up --detach postgres redis seaweedfs
cd apps/backend
uv sync --frozen
uv run --env-file ../../.env alembic upgrade head
uv run --env-file ../../.env uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
cd apps/web
npm ci
npm run dev
```

Open [the host frontend](http://localhost:3000). Next.js proxies `/api` to
localhost:8000. Set `BACKEND_URL` before dev/build if that address changes; the root
backend env file is not loaded by Next.js. The production rewrite is fixed at build time.

Run Celery workers and one Beat for email, imports, reminders and extraction. Exact
commands, alternate PostgreSQL ports and lifecycle guidance are in
[local development](docs/development/local-development.md).

## Migrations and verification

All schema changes use Alembic. For an intended **local development database**:

```bash
cd apps/backend
uv run --env-file ../../.env alembic current
uv run --env-file ../../.env alembic upgrade head
```

Do not run migration round trips on real data. Some downgrades intentionally reject
populated tables to avoid data loss. Back up deployed data before an approved upgrade.

Backend, from `apps/backend`:

```bash
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
```

For the **full** suite, supply disposable PostgreSQL/Redis/SeaweedFS through the
[test settings](docs/development/environment.md#isolated-test-configuration).
Without them, integration tests skip. CI provisions these services and exercises
migration round trips, metadata consistency, ownership and concurrent writes.

Frontend, from `apps/web`:

```bash
npm ci
npm run lint
npm run typecheck
npm run build
npx playwright install chromium
npm test
```

Browser tests use a production server on port 3001 and mock API responses. Linux
may need Playwright system dependencies. From the root also run
`docker compose config --quiet`. [CI](.github/workflows/ci.yml) builds/starts Compose
and checks routed health and worker readiness; it does not deploy.

## Documentation and limits

Start at the [documentation index](docs/README.md). Useful guides:

- [Local development](docs/development/local-development.md) and [ENV reference](docs/development/environment.md).
- [Backend](docs/architecture/backend.md), [frontend](docs/architecture/frontend.md) and [infrastructure](docs/architecture/infrastructure.md).
- [Workspace requirements](docs/product/workspace.md), [open decisions](docs/product/open-questions.md) and [ADRs](docs/adr/0004-keep-workspace-organization-optional.md).
- [Home hosting](docs/deployment/home-server.md) with Cloudflare Tunnel, HTTPS and no host ports; activation is a separate operator action.

This is a personal workspace, with no collaboration or production availability
promise. Schedule identity/coverage follows verified public IIS contracts. Personal
recurrence/all-day events and task planning are unfinished. Extraction supports text
PDF/DOCX/PPTX/TXT/MD, with 25 MiB/file and 1 GiB retained originals/user, without OCR.
Auth email has no durable outbox; queue loss requires resend/recovery. Automated
backups, redundancy and managed production deployment are not implemented.

Technical code/docs are English; initial product text is Russian. Reuse the approved
[A1 branding](assets/branding/README.md) for future screens.
