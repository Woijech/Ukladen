# Local Development

Status: foundation only. Review it before starting business-feature work.

## Prerequisites

- Docker Engine with Compose v2 and permission to access the daemon.
- uv 0.11.11 (or a compatible newer version) for backend host development.
- Python 3.14; install it with `uv python install 3.14` if needed.
- Node.js 22 and npm for frontend host development.
- Network access for dependency downloads and the initial source/image builds.

Local object storage uses the pinned SeaweedFS image; no storage source build is
required. The default configuration is a single-node development setup.

## Full stack

From the repository root:

```bash
cp .env.example .env
docker compose config --quiet
docker compose up --build --detach --wait --wait-timeout 180
docker compose ps
curl --fail http://localhost:8080/api/health/live
curl --fail http://localhost:8080/api/health/ready
curl --fail http://localhost:8080/health
```

Open `http://localhost:8080` for the shell and `http://localhost:8080/api/docs` for
API documentation. SeaweedFS's Admin UI is at `http://localhost:23646`, and its
S3 endpoint is `http://localhost:8333`. Admin UI credentials are
the local example values from `.env`; replace them for any shared deployment.
Keep PostgreSQL username/password/database values URL-safe when Compose assembles
the connection URL. `S3_ACCESS_KEY`/`S3_SECRET_KEY` configure both the S3 account and the local Admin UI.
`S3_BUCKET` is created automatically by `weed mini` on startup. S3 operations
require signed requests; the readiness probe is unauthenticated.

```bash
docker compose logs --follow api worker beat
docker compose exec -T worker celery -A app.workers.celery_app:celery_app inspect ping --timeout 5
docker compose exec -T api alembic current
docker compose down
```

Stopping the stack preserves database and object volumes. Source edits require an
image rebuild; the full stack runs built applications rather than source mounts.
No authentication or other business endpoints exist.

## Host development

Start only supporting containers, then run applications on the host:

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

Open `http://localhost:3000`; Next.js forwards `/api/*` to the host API. Set
`BACKEND_URL` before starting Next.js when using another backend address.

To run background processes from `apps/backend` in separate terminals:

```bash
uv run --env-file ../../.env celery -A app.workers.celery_app:celery_app worker --loglevel=INFO
uv run --env-file ../../.env celery -A app.workers.celery_app:celery_app beat --loglevel=INFO --schedule=/tmp/student-workspace-beat
```

Do not run host Beat together with Compose Beat. There are no periodic business jobs.

## Checks

From `apps/backend`:

```bash
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
```

From `apps/web`:

```bash
npm ci
npm run lint
npm run typecheck
npm run build
npx playwright install chromium
npm test
```

On Linux, Playwright may need system packages; `npx playwright install --with-deps
chromium` installs them where administrative access is available. Browser tests
start a production frontend on port 3001, which must be free.
Build before running tests. Backend unit tests do not require external services.

From the root: `docker compose config --quiet`. The CI workflow also builds and
starts the stack and checks routed HTTP probes. Run migration generation from
`apps/backend` with `uv run --env-file ../../.env alembic revision --autogenerate
-m "describe schema change"` only after adding real ORM models and importing them
into Alembic metadata. Review every generated migration.

## Deferred contracts

TODO: obtain verified IIS contracts before designing a schedule provider port or
adapter. No IIS fields, response payloads or fake business records are defined.
TODO: specify business schemas, HTTP contracts, authentication and AI tool contracts
in their respective future phases. Storage upload APIs and S3 adapters are not
implemented. Observability services and production deployment are not implemented.

## Upgrading an Existing MinIO Foundation

The provider replacement is documented in [ADR 0001](../adr/0001-use-seaweedfs.md).
Remove `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` from your local `.env`, set
`S3_ENDPOINT=http://localhost:8333`, and retain `S3_ACCESS_KEY`, `S3_SECRET_KEY` and
`S3_BUCKET`. Rebuild and refresh the stack with:

```bash
docker compose up --build --detach --remove-orphans --wait --wait-timeout 180
```

The old MinIO named volume is preserved. Its contents are not automatically
transferred to SeaweedFS; use an S3 client to migrate any objects before removing
the old volume. Do not attach the old volume to the SeaweedFS container.
