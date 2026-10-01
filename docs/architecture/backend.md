# Ukladen Backend Foundation

Status: foundation, auth contracts, persistence and password/token helpers implemented;
runtime business functionality is not implemented.

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
The `users` module owns the canonical `UserModel` with the required auth fields.
User status is `active` or `disabled`; PostgreSQL enforces case-insensitive email
uniqueness with a unique `lower(email)` index.

The auth module owns credentials, external identities, sessions and one-time tokens.
Foreign keys reference users and cascade on user deletion. Provider/subject pairs
and token hashes are unique. Session and one-time-token hash columns accept only
64 lowercase hexadecimal characters; expiry must be later than creation.
Timestamp columns are timezone-aware.
The initial identity provider is Google; the schema permits only `google` for now.

Alembic gets its URL from application settings. `0001_enable_vector` enables the
`vector` extension. `0002_auth_persistence` creates users and the four auth tables.
Alembic imports both modules' ORM models into its metadata. Schema changes must use
migrations. Compose runs migration once before starting API processes; HTTP
startup does not create tables.

## Authentication contracts

`modules/auth/domain` contains session and one-time-token data with no framework
imports. Validity checks use an explicit timezone-aware time and reject expired,
revoked, consumed or not-yet-valid values. Tokens expire at `expires_at`, not after
it. Session and token representations omit token hashes.

`OneTimeToken.consume` checks validity and records `used_at` on the domain object.
Atomic database consumption across concurrent requests is not implemented; it must
be enforced by persistence when token flows are added.

`modules/auth/application/ports.py` defines synchronous `PasswordHasher`,
`SessionRepository` and `SessionCache` protocols, matching the existing synchronous
database stack. The cache reuses the domain session data rather than a separate DTO.
`SqlAlchemySessionRepository` implements session creation, lookup and revocation.
It returns domain sessions, refreshes lookup results from PostgreSQL, and preserves
the first revocation timestamp on repeated revocation. It flushes new sessions but
does not commit: callers own transactions. Session validity checks remain separate
from persistence. Redis adapters, authentication services and endpoints are not implemented.
Browser sessions follow [ADR 0002](../adr/0002-use-opaque-browser-sessions.md).

`Argon2PasswordHasher` implements the password port using pwdlib's recommended
Argon2id settings and random salts. Verification returns false for incorrect
passwords and malformed or unsupported stored hashes. It does not log passwords
or hashes. Password policy and authentication endpoints are not implemented.

`generate_token` uses `secrets.token_urlsafe(32)` to generate opaque tokens from
32 cryptographically random bytes. `hash_token` returns a lowercase SHA-256 digest
for persistence and lookup. These helpers do not store or log the raw token;
session creation and token-delivery flows are not implemented.

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
Auth domain tests cover session expiry/revocation, one-time-token expiry and replay,
timezone-aware timestamps and omission of token hashes from object representations.
Security helper tests cover salted Argon2id hashes, correct/incorrect passwords,
malformed stored hashes, opaque token generation and a SHA-256 test vector.

PostgreSQL persistence tests cover the migration upgrade/downgrade, metadata drift,
case-insensitive email uniqueness, identity/token constraints, foreign keys, cascades,
session round trips (including IPv4/IPv6), and revocation. Set
`AUTH_TEST_DATABASE_URL` to a PostgreSQL Psycopg connection URL and run `uv run pytest`.
These tests skip when that variable is unset. Each test migrates a unique temporary
schema within a transaction that is rolled back afterward; existing tables and data
are not changed. The migration round trip retains the shared pgvector extension.
