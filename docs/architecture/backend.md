# Ukladen Backend Foundation

Status: foundation, auth contracts, persistence, password/token helpers, session
services and registration application flow implemented. HTTP authentication
endpoints and email delivery are not implemented.

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
`AUTH_SESSION_TTL_SECONDS` sets the lifetime used by `SessionService` and defaults
to 30 days (2,592,000 seconds). It must be positive. Cookie settings are not implemented.
`AUTH_PASSWORD_MIN_LENGTH` defaults to 12 characters and accepts values from 1 to
1024. Registration rejects passwords longer than 1024 characters before hashing.
`AUTH_EMAIL_VERIFICATION_TTL_SECONDS` defaults to 24 hours (86,400 seconds) and
must be positive. These settings are used by `RegistrationService`.

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
the first revocation timestamp on repeated revocation. Lookups acquire a PostgreSQL
row lock until transaction completion. Revocation returns affected token hashes,
including already-revoked sessions, so callers can retry cache invalidation.
It flushes new sessions but does not commit: callers own transactions.
Browser sessions follow [ADR 0002](../adr/0002-use-opaque-browser-sessions.md).

`Argon2PasswordHasher` implements the password port using pwdlib's recommended
Argon2id settings and random salts. Verification returns false for incorrect
passwords and malformed or unsupported stored hashes. It does not log passwords
or hashes. Registration enforces length limits without trimming passwords or
requiring particular character classes. Authentication endpoints are not implemented.

`generate_token` uses `secrets.token_urlsafe(32)` to generate opaque tokens from
32 cryptographically random bytes. `hash_token` returns a lowercase SHA-256 digest
for persistence and lookup. These helpers do not store or log the raw token.

`SessionService` creates sessions and returns an `IssuedSession` whose representation
omits the raw token. Creation does not publish to Redis; callers must commit before
delivering the token. Validation accepts the generated 43-character URL-safe token
format, checks Redis, then falls back to PostgreSQL. Invalid/expired/revoked sessions
are rejected. Token generation, hashing and the clock are injected; the service does
not import infrastructure adapters. `last_seen_at` is initialized at creation;
activity tracking is not implemented and validation does not update it.

`RedisSessionCache` uses Pydantic to serialize and validate domain session data.
Keys contain token hashes, not raw tokens. Entries expire at the session deadline.
Malformed, mismatched, expired or revoked entries are treated as cache misses.
Redis failures are sanitized into `SessionCacheUnavailable`; validation can proceed
from PostgreSQL when cache reads or writes fail.

Cache filling occurs while the PostgreSQL row lock is held. Revocation locks rows
and invalidates cache entries before commit, preventing a concurrent cache miss
from republishing an active session after successful revocation. Invalidation
failure propagates: callers must roll back instead of reporting successful logout.
Use short validation transactions and complete them before beginning mutation
transactions; commit mutations only after the service returns successfully.
Sessions must be revoked through the service to invalidate Redis. HTTP/cookie
integration, account-status checks and user-owned session endpoints are not implemented.

`RegistrationService` validates bare email addresses using the standard library,
trims surrounding whitespace and lowercases the email. It rejects display names,
comments, header injection, missing address parts and addresses longer than 320
characters. It preserves password whitespace and supports Unicode passwords.
It creates a user through the users-owned `UserRegistration` interface, then
persists an Argon2id credential, an opaque session and an email-verification token
through auth ports. The user remains active with `email_verified_at` unset.

`SqlAlchemyUserRegistration` uses PostgreSQL `ON CONFLICT DO NOTHING` against the
case-insensitive email index. A conflict becomes `RegistrationConflict`, without
overwriting or linking the existing account or exposing SQL exception details.
`SqlAlchemyRegistrationRepository` persists credentials and one-time tokens.
All adapters must share the same SQLAlchemy session and caller-owned transaction;
roll back on any error to avoid partial registration. None commits independently.

`RegistrationResult` carries user metadata and the raw session/verification tokens
for later delivery. Its representation hides both tokens. Only token hashes and
the password hash are persisted; registration does not publish session data to
Redis. Commit successfully before delivering cookies or verification email.
HTTP registration, cookies, CSRF/rate limiting, Celery email delivery and
verification confirmation remain unimplemented in this application-only step.

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

Session tests cover cache hits/misses, Redis failures, invalid cache data, expiry,
revocation and transaction rollback on invalidation failure. Set
`AUTH_TEST_REDIS_URL` to run the Redis integration check. PostgreSQL concurrency
tests use committed temporary schemas, drop them afterward, and exercise both
orders of cache filling versus revocation through separate connections and row locks.

Registration tests cover invalid inputs without side effects, configurable password
and verification-token limits, normalization, Argon2id persistence, hidden raw-token
representations, duplicate emails for accounts with/without passwords, and rollback
of all registration records after a late failure. PostgreSQL tests reuse the isolated
temporary-schema fixture and roll back their changes.
