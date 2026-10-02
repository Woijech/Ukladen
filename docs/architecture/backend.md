# Ukladen Backend Foundation

Status: foundation, auth contracts, persistence, password/token helpers, session
services, registration, email-verification, password-login and password-reset application flows implemented.
Browser password login/logout, session-management endpoints and CSRF bootstrap are implemented.
HTTP registration/verification/password-reset, email delivery and password change are not implemented.

The package is `apps/backend/src/app`, installed with uv on Python 3.14. FastAPI's
entrypoint is `app.main:app`. `create_app` accepts explicit settings for testing.
The application lifespan creates shared health clients, a SQLAlchemy engine and
session factory, and an Argon2 password hasher with a dummy hash generated once
at startup. Authentication reuses the health clients' Redis connection, closed by
their shutdown handler; the engine is also disposed on shutdown. Importing the API
does not connect to PostgreSQL/Redis or hash passwords.

## Configuration

`core/config.py` uses Pydantic Settings. Environment variables override a `.env`
in the process working directory. Required settings are `DATABASE_URL`, `REDIS_URL`,
`S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` and `S3_BUCKET`. URL types validate
connection settings. Object storage credentials use `SecretStr`. Configuration
must be supplied at startup; there are no hard-coded application credentials.
`AUTH_SESSION_TTL_SECONDS` sets the lifetime used by `SessionService` and defaults
to 30 days (2,592,000 seconds). It must be positive and also sets cookie lifetime.
`AUTH_PASSWORD_MIN_LENGTH` defaults to 12 characters and accepts values from 1 to
1024. Registration rejects passwords longer than 1024 characters before hashing.
`AUTH_EMAIL_VERIFICATION_TTL_SECONDS` defaults to 24 hours (86,400 seconds) and
must be positive. These settings are used by `RegistrationService`.
`AUTH_PASSWORD_RESET_TTL_SECONDS` defaults to one hour (3,600 seconds) and must
be positive. `PasswordRecoveryService` uses it for newly issued reset tokens.

`AUTH_SESSION_COOKIE_NAME` and `AUTH_CSRF_COOKIE_NAME` default to
`__Host-ukladen_session` and `__Host-ukladen_csrf`. Cookies are HttpOnly, use
`Path=/` without a domain, and default to `AUTH_COOKIE_SECURE=true` and
`AUTH_COOKIE_SAMESITE=lax` (`strict` is also supported). Names must be distinct;
`__Host-`/`__Secure-` names require Secure. `.env.example` explicitly selects
unprefixed cookie names and disables Secure for local HTTP development.
Settings validation errors omit input values to avoid exposing credentials.

`AUTH_ALLOWED_ORIGINS` is a JSON list of exact browser origins, with no credentials,
path, query or fragment. An empty list denies authentication mutations. Prefer
same-origin deployment; the API does not install CORS middleware.
`AUTH_LOGIN_RATE_LIMIT` defaults to 10 and `AUTH_LOGIN_RATE_WINDOW_SECONDS` to 60;
both must be positive.

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
Email verification and password reset use this check under a PostgreSQL row lock
and persist consumption in the same transaction as their user/credential updates.

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
requiring particular character classes. HTTP registration is not implemented.

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
Sessions must be revoked through the service to invalidate Redis. The authenticated
HTTP dependency validates the cookie and checks the canonical user's active status
in PostgreSQL on every request, including cache hits. Its short transaction completes
before the route starts a mutation transaction.

`SessionService.list_active_for_user` reads the authenticated user's sessions from
PostgreSQL, excluding revoked, expired and not-yet-valid rows. Results are ordered
by creation time descending, then UUID for ties. Listing does not update
`last_seen_at` or populate the cache. The HTTP response contains only the session
UUID, creation/last-seen/expiry timestamps, user agent, IP address and `is_current`.
It omits tokens, token hashes and user IDs.

`SessionService.revoke_for_user` uses a database update constrained by both session
and owner UUID, then invalidates the returned token hash through the existing cache
port. Missing and foreign sessions both become `SessionNotFound` and the same 404
response. Stored owned sessions can be revoked repeatedly, including expired or
already-revoked rows; the first revocation timestamp is preserved and invalidation
is retried. Callers own transactions and must roll back cache failures. DELETE
returns 204 only after commit and clears the cookie only for the current session.
Deleting another session leaves the current cookie intact. An authenticated
session is required, including for repeated deletion.

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
HTTP registration, Celery email delivery and HTTP verification confirmation remain
unimplemented. Cookie delivery, CSRF protection and rate limiting are implemented
for password login.

`EmailVerificationService` accepts the generated 43-character URL-safe token format
and looks up only its hash through `EmailVerificationRepository`. The SQLAlchemy
adapter selects email-verification tokens with `FOR UPDATE` and refreshes their
state. The service checks expiry and consumes the domain token after acquiring the
lock, so time spent waiting cannot allow an expired token through. Unknown,
expired, already-used, not-yet-valid and password-reset tokens are rejected.

`SqlAlchemyEmailVerifier` implements the users-owned `EmailVerifier` interface.
It records `email_verified_at`, preserves any earlier verification timestamp and
does not change user status. Both adapters must share one SQLAlchemy session and
caller-owned transaction. Commit only after confirmation succeeds; roll back any
exception, including a missing or failed user update. Token-row locks remain held
until transaction completion, so concurrent confirmations cannot both consume a
token. A failed transaction leaves the token available for retry. The service
returns only the user UUID and does not log or persist the raw token.

`LoginService` shares registration's email normalization and preserves password
whitespace. Login accepts passwords from 1 to 1024 characters; it does not apply
the current registration minimum to existing credentials. Malformed inputs,
unknown emails, incorrect passwords, disabled accounts and accounts without a
usable password credential all produce `Invalid email or password.`

`SqlAlchemyUserAuthentication` returns an active user UUID through the users-owned
`UserAuthentication` interface. `SqlAlchemyCredentialRepository` returns the stored
hash through `CredentialRepository`. Both lookups acquire PostgreSQL row locks,
in user-then-credential order, held until the caller completes the transaction.
This prevents the selected user status or credential changing between lookup and
session creation. All adapters must share the same SQLAlchemy session. Roll back
on failure and commit before delivering a session token.

Login verifies a supplied dummy Argon2 hash when no active user/password credential
is found, reducing the timing difference from skipping password verification.
HTTP startup generates that hash once with the same password hasher.
Matching the dummy hash cannot authenticate
an account without a real credential. Unverified active users can log in.
Successful login returns the existing `IssuedSession` DTO and stores only the
opaque token hash. It does not publish the new session to Redis.

Application logout uses the existing `SessionService.revoke`; logout-all uses
`SessionService.revoke_all_for_user`. Both invalidate Redis within the caller-owned
transaction. HTTP login delivers its cookie only after commit; logout/logout-all
clear the cookie only after successful revocation and commit. Failed cache
invalidation rolls back revocation and retains the browser cookie for retry.

`PasswordRecoveryService.request_reset` reuses email normalization and locks the
active user and existing credential in that order. Malformed/unknown emails,
disabled users and accounts without password credentials return no delivery data
and create no token. Eligible accounts receive a new password-reset token with
only its SHA-256 hash persisted. The service returns `PasswordResetDelivery` for
internal delivery after commit; its representation hides the raw token. It must
never be returned from HTTP or logged. No email is sent or queued in this step.

`confirm_reset` accepts the generated 43-character URL-safe token format and applies
the current registration password-length policy while preserving whitespace and
Unicode. It hashes the new password before acquiring database locks. Token lookup
selects only password-reset rows with `FOR UPDATE` and refreshes their state,
reusing the email-verification adapter's private lookup and consumption helpers.
The service then locks the active user and existing credential, checks expiry
after all locks are acquired, and consumes the token through the domain method.
It updates the credential's hash, `password_updated_at` and `updated_at`, preserves
`created_at`, marks the token used and revokes all of that user's sessions through
`SessionService`. It does not create credentials, verify email, change user status
or link external identities. Invalid/expired/used/wrong-type tokens and ineligible
accounts produce the same `Invalid or expired token.` error.

All reset adapters share one SQLAlchemy session and caller-owned transaction.
The caller must commit on success and roll back every exception, including failed
credential updates and cache invalidation. A rollback preserves the old password,
unused token and unrevoked sessions so confirmation can be retried. Locks remain
held until transaction completion; concurrent confirmations cannot both consume
the same token. Reset confirmation returns only the user UUID.

Status: HTTP password-reset request/confirmation and email delivery are not
implemented. Their future transport must return a generic request acknowledgement
regardless of account existence, add CSRF/rate protection, and deliver reset email
asynchronously through an `EmailSender` boundary after commit. Provider selection
and public reset integration remain TODOs; the current service has no mail-vendor
dependency. Password change is a separate, unimplemented flow.

## HTTP

| Endpoint | Behavior |
| --- | --- |
| `GET /api/health/live` | Always returns 200 while the API can serve requests. |
| `GET /api/health/ready` | Checks PostgreSQL, Redis and SeaweedFS; returns 200 or 503. |
| `GET /api/docs` | Interactive Swagger UI. |
| `GET /api/openapi.json` | Generated OpenAPI schema. |
| `GET /api/v1/auth/csrf` | Sets/reuses an HttpOnly CSRF cookie and returns its token. |
| `POST /api/v1/auth/login` | Password login; returns user/session IDs and expiry, and sets a session cookie. |
| `POST /api/v1/auth/logout` | Revokes the current session, clears its cookie and returns 204. |
| `POST /api/v1/auth/logout-all` | Revokes the current user's sessions, clears the cookie and returns 204. |
| `GET /api/v1/auth/sessions` | Lists only the authenticated user's active sessions and public metadata. |
| `DELETE /api/v1/auth/sessions/{session_id}` | Revokes an owned session; returns 204 or a generic 404. |

Authentication POST and DELETE requests require an exact allowed `Origin` and matching
43-character URL-safe tokens in the CSRF cookie and `X-CSRF-Token` header, compared
in constant time. CSRF bootstrap rejects `Sec-Fetch-Site: cross-site` and reuses an
existing valid token. The JSON token enables header submission while the cookie
remains HttpOnly. Clients must include cookies. Production `__Host-` cookies also
prevent subdomains from injecting domain-scoped authentication cookies.

`RedisRateLimiter` uses an atomic INCR/EXPIRE Lua script for fixed login windows;
denied attempts do not extend expiry. It keys limits by the hash of the ASGI peer
address and does not parse forwarded headers itself. Configure trusted proxy
handling at the server when deploying behind a proxy, or clients share the proxy's
limit. Exceeded limits return 429 with `Retry-After`; unavailable or invalid Redis
limiter state fails closed with a sanitized 503 response.

Login returns Pydantic DTOs without raw session tokens or hashes; the token appears
only in `Set-Cookie`. Password input uses `SecretStr` and is hidden from DTO
representations. Session metadata uses the parsed peer IP and a user agent capped
at 1024 characters. Credentials produce a generic 401; invalid/expired sessions
and inactive users produce 401 and clear the session cookie. Repeating logout
without a valid cookie therefore returns 401. SQL/cache/limiter failures return
503 without connection details. Request validation returns a generic 422 without
echoing input, including malformed JSON. Token-bearing responses, authentication
results and these sanitized error responses use `Cache-Control: no-store`.
CSRF rejection returns 403.

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

Email-verification tests cover malformed tokens, hashed lookup, expiry after lock
acquisition, replay, future/expired/wrong-type tokens, preservation of prior
verification and user status, and rollback when the user update fails. PostgreSQL
concurrency tests exercise a blocked second confirmation, rejection after the
first commits, and successful retry after the first rolls back.

Login tests cover generic rejection errors, dummy verification without authentication,
input limits, existing passwords shorter than the registration minimum, Unicode and
whitespace preservation, login before email verification, session metadata and
hash-only storage. PostgreSQL checks cover malformed/missing credentials, disabled
accounts, rollback after session insertion, and user/credential locks until commit.
Integration tests exercise login followed by logout and logout-all, including Redis
invalidation and preservation of another user's sessions.

HTTP tests cover cookie flags, CSRF/origin rejection, generic secret-safe errors,
rate limits, commit failure, logout transaction boundaries and inactive users.
With both integration URLs set, they also exercise complete browser flows against
PostgreSQL/Redis in isolated temporary schemas, including replay rejection, account
disabling, Redis validation fallback and revocation rollback/retry. Redis tests
verify the native limiter's window and expiry and remove their generated test keys.

Session-management tests cover safe response fields, current-session identification,
authentication/CSRF requirements, UUID validation, generic 404/503 errors and cookie
delivery after transaction completion. PostgreSQL/Redis checks cover ownership,
expired/revoked/future exclusion, exact expiry boundaries, repeated revocation,
cache invalidation, rejected token replay, preservation of another user's sessions
and rollback/retry when cache invalidation fails.

Password-reset tests cover eligibility, normalization, configurable lifetime and
password limits, hidden raw tokens, hash-only persistence, Unicode/whitespace
preservation, malformed/wrong-type/expired/future/used tokens and expiry after lock
acquisition. PostgreSQL/Redis checks cover credential timestamps, token consumption,
revocation of all owned sessions without affecting another user, rollback/retry on
cache failure, replay rejection and competing confirmations after commit/rollback.
They also verify that user and credential locks remain held until commit.
