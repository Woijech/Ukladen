# Backend Foundation

Status: foundation implemented; business modules are not implemented.

The package is `apps/backend/src/app`, installed with uv on Python 3.14. FastAPI's
entrypoint is `app.main:app`. `create_app` accepts explicit settings for testing.
The application lifespan creates shared health clients, a SQLAlchemy engine and
session factory, then disposes them on shutdown. Importing the API does not connect
to PostgreSQL or Redis.

## Configuration

`core/config.py` uses Pydantic Settings. Environment variables override a `.env`
in the process working directory. Required settings are `DATABASE_URL`, `REDIS_URL`,
`S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` and `S3_BUCKET`. URL types validate
connection settings. Object storage credentials use `SecretStr`. Configuration
must be supplied at startup; there are no hard-coded application credentials.

## Database

`db/session.py` owns the SQLAlchemy declarative base, synchronous Psycopg engine
and session factory. The factory is available as `app.state.session_factory`.
There are no repositories or ORM business models yet. Future module-owned ORM
models must be imported into Alembic metadata when their migrations are added.

Alembic gets its URL from application settings. `0001_enable_vector` enables the
`vector` extension. Schema changes must use migrations. Compose runs migration
once before starting API processes; HTTP startup does not create tables.

## HTTP

| Endpoint | Behavior |
| --- | --- |
| `GET /api/health/live` | Always returns 200 while the API can serve requests. |
| `GET /api/health/ready` | Checks PostgreSQL, Redis and SeaweedFS; returns 200 or 503. |
| `GET /api/docs` | Interactive Swagger UI. |
| `GET /api/openapi.json` | Generated OpenAPI schema. |

Responses are Pydantic DTOs. The readiness service performs checks outside route
handlers. Dependency failures are returned as booleans without connection details.
Probes use three-second connection/request limits; PostgreSQL also has a statement
timeout. Storage uses the S3 gateway's `/readyz` endpoint. Probes check connectivity,
not business schema completeness, bucket permissions, worker availability or
Beat scheduling.

## Background processes

`workers/celery_app.py` configures a Redis broker, JSON serialization, UTC and no
result backend. `foundation.ping` is an idempotent diagnostic task returning `pong`.
Beat runs the same app with an empty periodic schedule. Business jobs and periodic
tasks are not implemented. Redis does not hold authoritative user data.

## Verification

Ruff checks imports/style and formatting; Pyright checks source, migrations and
tests. pytest covers liveness, readiness success/failure, sanitized failures,
OpenAPI and invalid connection settings without requiring external services.
