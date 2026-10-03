# Ukladen Backend Foundation

Status: foundation, auth contracts, persistence, password/token helpers, session
services, registration, email-verification, password-login, password-reset and
password-change application flows implemented.
Browser registration, password login/logout/change, email-verification request/confirmation,
password-reset request/confirmation, session-management endpoints and CSRF
bootstrap are implemented.
Celery email queuing, a development fake and configurable SMTP delivery are implemented.
A Google OIDC identity adapter, account-resolution application service and
browser-bound Redis OAuth state and Google browser login are implemented.
Explicit Google linking is implemented. A deployment must supply its SMTP service;
browser email verification is implemented. Other frontend authentication UI and
durable email publication recovery are not implemented.

The package is `apps/backend/src/app`, installed with uv on Python 3.14. FastAPI's
entrypoint is `app.main:app`. `create_app` accepts explicit settings for testing.
The application lifespan creates shared health clients, a SQLAlchemy engine and
session factory, a Celery producer and an Argon2 password hasher with a dummy hash
generated once at startup. Authentication reuses the health clients' Redis
connection, closed by their shutdown handler; the Celery producer is closed and
the engine disposed on shutdown. Importing the API does not connect to
PostgreSQL/Redis or hash passwords.

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
`AUTH_REGISTER_RATE_LIMIT` defaults to 5 and `AUTH_REGISTER_RATE_WINDOW_SECONDS`
to 60; both must be positive. Registration uses the hashed ASGI peer address with
a separate Redis key namespace.
`AUTH_PASSWORD_CHANGE_RATE_LIMIT` defaults to 5 and
`AUTH_PASSWORD_CHANGE_RATE_WINDOW_SECONDS` to 60; both must be positive.
Password-change limits are keyed by the authenticated user UUID, shared across
that user's sessions and client addresses.
`AUTH_EMAIL_VERIFICATION_CONFIRM_RATE_LIMIT` defaults to 5 and
`AUTH_EMAIL_VERIFICATION_CONFIRM_RATE_WINDOW_SECONDS` to 60; both must be positive.
Confirmation limits use the hashed ASGI peer address and a separate Redis key
namespace from login.
`AUTH_EMAIL_VERIFICATION_REQUEST_RATE_LIMIT` defaults to 5 and
`AUTH_EMAIL_VERIFICATION_REQUEST_RATE_WINDOW_SECONDS` to 60; both must be positive.
Resend limits are keyed by the authenticated user UUID, shared across sessions and
client addresses, in their own Redis namespace.
`AUTH_PASSWORD_RESET_CONFIRM_RATE_LIMIT` defaults to 5 and
`AUTH_PASSWORD_RESET_CONFIRM_RATE_WINDOW_SECONDS` to 60; both must be positive.
Reset-confirmation limits also use the hashed ASGI peer address, with their own
Redis key namespace.
`AUTH_PASSWORD_RESET_REQUEST_RATE_LIMIT` defaults to 5 and
`AUTH_PASSWORD_RESET_REQUEST_RATE_WINDOW_SECONDS` to 60; both must be positive.
Request limits use the hashed ASGI peer address with a separate Redis key namespace.
`AUTH_EMAIL_DELIVERY_MODE` accepts `disabled` (the default), `fake` or `smtp`.
`.env.example` explicitly enables the development fake; existing `.env` files
are not modified. Disabled mode refuses email queuing and worker delivery with
`EmailDeliveryUnavailable`. Fake mode sends no external email.

`AUTH_EMAIL_VERIFICATION_URL` optionally enables email links to the frontend
`/auth/verify-email` page. It must use an allowed origin, HTTPS except loopback
development, and no credentials, query or fragment. The worker appends the token
as `#token=...` to the configured URL. If unset, manual token-only verification
emails remain available. `.env.example` sets the local frontend URL; existing
deployments must configure their public URL explicitly.

SMTP mode requires `SMTP_HOST` and a bare `SMTP_FROM_EMAIL`. `SMTP_USERNAME` and
`SMTP_PASSWORD` must be configured together when authentication is needed; both
use `SecretStr` and are omitted from settings representations. `SMTP_PORT` defaults
to 587 and accepts 1–65535. `SMTP_SECURITY` defaults to `starttls`, also accepts
`tls` (implicit TLS, normally port 465) or `none` for a trusted local development
receiver. Authentication without TLS is rejected. `SMTP_TIMEOUT_SECONDS` defaults
to 10 and must be finite, positive and at most 60. Required SMTP fields and the
sender address are validated at startup in SMTP mode. No SMTP connection occurs
in the API process, during import or during settings validation. See
[auth email setup](../development/auth-email.md).

`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` and `GOOGLE_REDIRECT_URI` are optional
as a group: all must be unset or all supplied. The secret uses `SecretStr` and is
omitted from settings representations. Callback URIs disallow credentials, query
strings and fragments; HTTPS is required except for `localhost`, `127.0.0.1` and
`[::1]` development URLs. Commented placeholders are provided in `.env.example`.
The Google adapter consumes these settings; it is not wired into browser routes yet.

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
requiring particular character classes.

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
`POST /api/v1/auth/register` wires this service with the users-owned registration
adapter, credential/token repository, existing password hasher and session service,
all sharing one SQLAlchemy session. Its DTO rejects extra fields, bounds email to
1–320 characters and wraps the password in `SecretStr` with 1–1024 bounds; the
application enforces the configured registration minimum. CSRF validation and a
configurable peer-address Redis limiter run before mutation. Disabled email delivery
fails closed with a sanitized 503 before creating any records.

The route commits the complete registration before delivering the HttpOnly cookie
through the same setter as login and calling `EmailSender.send_email_verification`.
It returns 201 with only user UUID, session UUID and expiry, plus `Cache-Control:
no-store`; raw tokens and hashes never appear in response JSON. User agents are
capped at 1024 characters and IP addresses come from the ASGI peer. Registration
does not require or validate an existing session cookie. New users remain active
and can log in before email verification.

Invalid registration input returns a fixed 400, duplicate accounts a fixed 409,
and invalid transport a generic 422. Database or commit failure returns a sanitized
503 without issuing a cookie or queuing mail; all registration records roll back.
Existing password, Google-only and disabled accounts are never overwritten or
linked. If publication fails after commit, the account and session remain valid
and the route retains 201/cookie delivery. The warning contains only a fixed message,
user UUID and event, without recipient, token or exception traceback. There is no
transactional outbox; a failed publication can leave an unverified account without
delivered verification mail. The authenticated resend endpoint permits a new request.
SMTP delivery is available through the worker. Configurable verification requirements
for sensitive features remain unimplemented.

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

`POST /api/v1/auth/email-verification/confirm` calls this existing service through
`get_email_verification`, sharing one SQLAlchemy session between its adapters and
the route's transaction. It requires CSRF validation and the peer-address Redis
rate limiter; no authenticated session is required or validated. The DTO accepts
only a `token` field, uses `SecretStr`, hides it from representations and requires
43 characters. The service enforces the URL-safe format. Confirmation returns an
empty 204 with `Cache-Control: no-store` only after commit; it does not set or clear
session cookies, create sessions or change user status. Invalid/unknown/expired/
future/used/wrong-type tokens receive the same fixed 400. Malformed transport
input receives the existing generic 422 without echoing the token. Rate limits
return 429 with `Retry-After`; database/limiter failures return a sanitized 503.
These responses use `Cache-Control: no-store` and do not expose tokens or user IDs.
CSRF rejection returns 403 before rate limiting or confirmation.

`EmailVerificationRequestService.request` uses the users-owned `EmailVerifier`
lookup to read and lock an active, unverified user's canonical email by UUID. It
returns no delivery data for missing, disabled or already verified users. Eligible
users receive a new email-verification token with the configured lifetime, computed
after acquiring the user lock. `SqlAlchemyRegistrationRepository` stores only its
SHA-256 hash within the same caller-owned transaction. `EmailVerificationDelivery`
is internal and hides the raw token from its representation; callers must commit
before sending. Requesting another token leaves all earlier tokens untouched and
valid until their original expiry. Each token can be consumed only once.

`POST /api/v1/auth/email-verification/request` requires an authenticated active
session, CSRF validation and per-user Redis limiting. Its DTO accepts only an empty
JSON object; recipient email and user IDs cannot be supplied. The route uses the
current session's user UUID, commits token creation, then queues through the existing
`EmailSender`. Eligible and already verified users receive the same 202 with
`Email verification request accepted.` and `Cache-Control: no-store`; neither sets
nor clears the session cookie. Invalid sessions receive the existing 401 and cookie
clearing, CSRF rejection 403, malformed transport 422, and rate rejection 429 with
`Retry-After`. Database/commit, limiter and disabled delivery failures return the
sanitized 503; no mail is queued or token committed on issuance failure. After-commit
queue failure retains 202 and logs only a fixed message, user UUID and failure event,
without recipient, token or traceback. A subsequent request can issue a fresh token;
durable publication recovery remains unimplemented.

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

`POST /api/v1/auth/password-reset/confirm` calls `confirm_reset` through the existing
`get_password_recovery` dependency and its shared SQLAlchemy session. The route
owns one transaction and returns an empty 204 with `Cache-Control: no-store` only
after commit. It then clears the browser session cookie without creating a new
session. No login or session validation is required: the reset token authorizes
the change. CSRF validation and the peer-address Redis limiter run before the
service. The request DTO forbids extra fields, hides both `SecretStr` values from
representations, requires a 43-character token and bounds the new password to
1–1024 characters. The application validates the URL-safe token format and the
configured password minimum. Invalid/expired/used/wrong-type tokens and ineligible
accounts receive a fixed 400; password-policy failures receive a separate fixed
400. Invalid request bodies receive the existing generic 422 without echoing
secrets. Rate limiting returns 429 with `Retry-After`; database/cache/limiter
failures return a sanitized 503. These responses use `Cache-Control: no-store`.
Failures do not clear or replace the cookie, allowing a rolled-back reset to be
retried. CSRF rejection returns 403 before rate limiting or confirmation.

`POST /api/v1/auth/password-reset/request` accepts a DTO containing only `email`,
bounded to 1–320 characters. It requires CSRF and the peer-address Redis limiter
before lookup. `get_email_sender` refuses disabled delivery with the generic 503
before invoking the application service, regardless of account existence. No
login or session validation is required. With fake or SMTP delivery enabled, eligible,
unknown, disabled, passwordless and malformed bare-email outcomes all return the
same 202 Pydantic acknowledgement: `Password reset request accepted.` The response
uses `Cache-Control: no-store`, omits internal delivery data and preserves cookies.

The route owns the token-creation transaction and calls `EmailSender.send_password_reset`
only after commit, only when the service returns eligible delivery data. Database
or commit failure returns a sanitized 503 and does not enqueue. If publication
fails after commit, the token remains committed and the response remains the same
202, so queue health cannot disclose account eligibility. The warning contains
only a fixed message, user UUID and failure event; it does not include email,
token or exception details. Clients can retry to issue a new token. Without an
outbox, a process crash or broker failure can lose a message; no durable delivery
or automatic retry is claimed. Transport validation returns generic 422, CSRF
rejection 403, and rate rejection 429 with `Retry-After`. Delivery uses the configured
worker adapter; the application service has no mail-vendor dependency.

`PasswordRecoveryService.change_password` requires the current password and an
owned current-session UUID. Current passwords accept 1 to 1024 characters so
existing credentials remain usable after the registration minimum changes. New
passwords use the same private validation/hashing helper as reset confirmation,
with the configured minimum, a maximum of 1024 characters and preserved whitespace
and Unicode. The new hash is computed before acquiring database locks.

The service locks the active user and credential, verifies the current password
and updates the existing credential and its timestamps. Disabled users, missing
or malformed credentials and incorrect current passwords produce the same
`Invalid current password.` error. It does not create credentials or link accounts.
It then calls `SessionService.revoke_others_for_user`. This service locks the
retained session directly in PostgreSQL with both session/owner UUIDs and checks
expiry after acquiring the lock, bypassing Redis. A missing, foreign, expired,
revoked or future retained session raises `InvalidSession` and the caller must
roll back the credential update.

Revocation updates only the user's other sessions and invalidates their cache
entries before commit, including already-revoked sessions for retry. The first
revocation timestamp is preserved. The current session's token, cache entry,
expiry and metadata remain unchanged; another user's sessions are unaffected.
User, credential and retained-session locks remain held until transaction
completion. Concurrent changes recheck the current password after waiting for
the user lock. The caller must roll back every error, including cache invalidation
failure. If there are no other sessions, no Redis deletion is needed.
`POST /api/v1/auth/password/change` wires this service through the existing
SQLAlchemy session, password hasher and session service. It requires authentication,
CSRF validation and the per-user Redis rate limiter before invoking password change.
Its request DTO uses `SecretStr` for both passwords, omits them from representations,
rejects extra fields and bounds both inputs to 1–1024 characters. The application
enforces the configured minimum for new passwords. It returns an empty 204 only
after commit, with `Cache-Control: no-store`, and does not set or clear the current
cookie. Invalid current passwords return a fixed 401; policy failures return a
fixed 400. Transport validation returns the existing generic 422; invalid sessions
use the existing 401 handler and clear the cookie. Rate limits return 429 with
`Retry-After`; limiter/cache/database failures return a sanitized 503. Responses
omit passwords, tokens and internal exception details.

## Google OIDC adapter

`ExternalIdentityProvider` is the application boundary for authorization URL building
and callback resolution. `GoogleOidcProvider` implements it using a caller-owned
HTTPX client; construction performs no I/O and disabled settings fail closed.
The caller must validate and consume browser-bound OAuth state before invoking
`resolve_callback`. This adapter neither owns browser state nor creates or links
Ukladen accounts/sessions. Google browser routes use this adapter through
`GoogleOAuthService`, which consumes state before exchanging the authorization code.

The adapter follows [Google's documented OIDC server flow](https://developers.google.com/identity/openid-connect/openid-connect).
It obtains authorization, token and JWKS endpoints from the fixed Google discovery
URL, validates the issuer and RS256/S256 support, and restricts endpoints to HTTPS
on their expected Google hosts without credentials, ports, query strings or
fragments. Redirect following is disabled. Authorization URLs carry only the client
ID, configured redirect URI, `openid email` scopes, code response type, state, nonce
and S256 PKCE challenge. State, nonce and challenge must be 43-character URL-safe
tokens. The future browser flow is responsible for generating/storing state and
nonce and deriving the challenge from the verifier.

Callback resolution bounds the authorization code and checks the nonce and PKCE
verifier before I/O. The code exchange posts credentials/code/verifier in form data
with `authorization_code` grant type, using the configured redirect URI. Requests
use three-second timeouts and provider JSON bodies are limited to 64 KiB. Invalid
code responses (400/401) become `InvalidExternalIdentity`; communication, malformed
JSON, unexpected status and invalid discovery data become fixed
`ExternalIdentityUnavailable` errors. The adapter performs no code-exchange retries.

`PyJWT[crypto]>=2.13,<3` adds PyJWT and cryptography for RSA/JWT validation, reusing
HTTPX for transport. The locked versions are PyJWT 2.15.1 and cryptography 50.0.2.
ID tokens are bounded to 16 KiB; only RS256 with a nonempty bounded `kid` is accepted.
Unsupported critical headers are rejected; token-provided key URLs are ignored.
JWKS selection requires exactly one matching RSA signing key, compatible algorithm
and verification use, no private key material and a minimum 2048-bit public key.
An unknown key ID triggers one JWKS refresh before rejection, supporting rotation.
PyJWT validates signature, Google issuer, exact client audience, expiry and issue
time. Required claims include issuer, subject, audience, expiry, issue time, nonce,
email and verification status. The adapter additionally requires a bounded ASCII
subject, integer issue/expiry timestamps in order, matching authorized presenter
when present, constant-time nonce equality and a strictly boolean true
`email_verified`. Email validation/normalization reuses registration's standard
library helper. Invalid claims/signatures become a fixed `InvalidExternalIdentity`
without exposing provider content or chained exception text.

`VerifiedGoogleIdentity` contains only subject and normalized email. Provider access,
refresh and ID tokens are neither returned nor persisted/logged. Public discovery and
JWKS documents are cached per adapter using monotonic expiry, respecting max-age,
Age, no-store and no-cache, with a one-hour ceiling. Expired data is refetched and
is not served on provider failure. Cache fills share one lock; replicas may fetch
the same public data independently. The caller owns HTTP client cleanup.

## Browser-bound OAuth state

`OAuthStateService.start` generates independent random state, nonce, PKCE verifier
and browser-binding tokens using the existing token helper. S256 produces the
unpadded base64url SHA-256 verifier challenge. `OAuthStateStart` returns only the
internal data needed to build the authorization URL and set a browser cookie;
the verifier stays in the temporary `OAuthStateRecord`. Both DTOs redact their
fields from representations. HTTP routes deliver the binding token in an HttpOnly cookie.

`OAuthStateStore` is the application boundary for temporary storage.
`RedisOAuthStateStore` uses `ukladen:auth:oauth:<SHA-256(state)>` keys. The JSON value
contains a SHA-256 browser-token hash and the nonce/verifier needed for provider
validation. Redis `SET NX EX` creates a record without overwriting another flow.
`AUTH_OAUTH_STATE_TTL_SECONDS` defaults to 600 and must be positive. Redis expiry
is authoritative for this temporary state; PostgreSQL is unaffected.

Consumption validates callback token formats before I/O, bounds and validates
the stored JSON, then compares the browser hash in constant time. A mismatched
browser cannot delete the valid record. A Lua compare-and-delete consumes only
the exact record read, so simultaneous callbacks have one winner and expiry or
replacement between read and delete fails closed. Missing, expired, consumed and
mismatched states raise the same fixed `InvalidOAuthState`. Redis failures or failed
creation raise fixed `OAuthStateUnavailable` without chained connection details.
There is no process-local fallback and no token logging.

Browser routes deliver the binding token through a Secure HttpOnly SameSite=Lax
cookie (Secure may be disabled for local development), consume state before
provider exchange/account mutation, and require restarting login after a
consumed-state provider failure.

## Google account resolution

`GoogleLoginService` accepts only `VerifiedGoogleIdentity`, after provider and
browser-state validation. It uses the Google subject to resolve an existing
identity through `GoogleIdentityRepository`; linked users must be active under
the canonical users-module row lock. The Google email cannot replace their
Ukladen email, verification status, credentials or profile.

For an unlinked subject with an unused normalized email, the service creates a
user through the users-module registration port, marks the email verified,
inserts a Google identity and creates an ordinary opaque session. No password
credential or email-verification token is created. All adapters share one caller-owned
transaction; callers must roll back on any failure and commit before delivering
the returned `IssuedSession`. Session creation does not publish Redis data.

An existing email raises `AccountLinkingRequired`, including password, Google-only
and disabled accounts. Explicit password re-authentication and linking use the
separate flow below; normal Google login never implicitly links.
The existing email and provider/subject uniqueness constraints arbitrate concurrent
creation. After an email conflict, the service rechecks the subject so two first
logins for the same identity can authenticate the winning account. A subject conflict
with a different candidate email fails without overwriting the identity; rollback
removes the losing candidate user, and a retry resolves the linked subject.
Provider tokens never enter account resolution. The Google callback invokes this
service only after state and provider validation, with one database transaction.

## Google browser login

`GET /api/v1/auth/google/start` rejects cross-site initiation and untrusted Origin
headers, applies the per-peer Redis rate limit, creates state, sets the binding
cookie and redirects to Google. `GET /api/v1/auth/google/callback` accepts the
cross-site provider redirect, bounds/redacts query data, rejects duplicate code,
state or error parameters, consumes state and verifies the provider before opening
the account-resolution transaction. Commit precedes session cookie delivery.
Responses use 303 redirects, `Cache-Control: no-store` and `Referrer-Policy: no-referrer`.
The successful callback clears the OAuth cookie and redirects to the configured
success URL. Failed callbacks redirect to the configured error URL, preserve
existing session cookies and leave the binding cookie to expire or be replaced
by the next initiation. They do not expose provider/error input. Rate-limit
failures return 429 with Retry-After; unavailable configuration/protection returns 503.

`FRONTEND_AUTH_SUCCESS_URL` and `FRONTEND_AUTH_ERROR_URL` must be configured
together. Both require HTTPS except local loopback HTTP and prohibit credentials,
query strings and fragments. They are fixed configuration, never request return URLs.
Google browser login fails closed until provider and frontend settings are configured.
`AUTH_OAUTH_COOKIE_NAME` defaults to `__Host-ukladen_oauth`, distinct from session
and CSRF cookies. Enabled OAuth cookies obey Secure prefix rules and always use
SameSite=Lax, HttpOnly, Path=/, no Domain, and the state lifetime. Local HTTP must
select an unprefixed name. Existing deployments with Google disabled need no new
cookie configuration. Start and callback independently default to 10 attempts
per 60 seconds, using `AUTH_GOOGLE_START_RATE_LIMIT` /
`AUTH_GOOGLE_START_RATE_WINDOW_SECONDS` and `AUTH_GOOGLE_CALLBACK_RATE_LIMIT` /
`AUTH_GOOGLE_CALLBACK_RATE_WINDOW_SECONDS` (positive values).

The application lifespan conditionally constructs the provider using the existing
HTTP client and closes it with health clients. Construction makes no Google requests.
`AuthAccessLogFilter` removes authentication query strings from Uvicorn access
records while preserving path/status/peer metadata. Reverse proxies must likewise
omit authentication query strings from access logs; the current Traefik configuration
does not enable access logging.

## Explicit Google linking

`POST /api/v1/auth/google/link/start` requires an authenticated session, Origin/CSRF
validation, current password and a per-user rate limit. `GoogleLinkService.prepare`
locks the active canonical user, credential and current session in that order,
verifies the password with Argon2id (using the startup dummy hash for accounts
without credentials), then rechecks session expiry/revocation. It returns an
`OAuthLinkContext` containing user/session UUIDs and SHA-256 of the credential hash,
never the password or credential hash itself. Password fingerprints are redacted.
The caller completes this transaction before invoking Google/network initiation.
The context lives only inside the expiring browser-bound Redis state and is
returned internally with the verified identity as `GoogleCallbackResult`.
Old ordinary-login state without a link context remains compatible.

The shared callback selects linking only from the consumed server-side context.
`GoogleLinkService.complete` locks user, credential and the original session,
requires the incoming session cookie to match that session, checks status,
expiry/revocation and the unchanged credential fingerprint, and only then inserts
the identity and creates an ordinary session for that user. A subject already
owned by this user is idempotent; an identity owned by another user cannot be
transferred. Provider/subject uniqueness arbitrates competing users; failure
rolls back both identity and new session. Cookie delivery follows commit. The old
session is retained. User email, verification state, profile and credentials are
preserved, including when the explicitly selected Google email differs.

Logout/revocation, expiry, switching sessions, disabling the user or changing/resetting
the password invalidates the pending link. Callback checks PostgreSQL even if Redis
still contains a cached session. State is single-use; failures require fresh initiation.
Google-only users cannot use this password re-authentication flow. Attaching other
identities to Google-only accounts and unlinking are outside the current scope.

`GoogleLinkRequest` accepts only `current_password` as a redacted SecretStr;
caller-supplied user/identity IDs are rejected. Linking requires session cookies
with SameSite=Lax, so the original session reaches the cross-site callback.
Strict-cookie configurations fail closed before link initiation.
`AUTH_GOOGLE_LINK_RATE_LIMIT` defaults to 5 and
`AUTH_GOOGLE_LINK_RATE_WINDOW_SECONDS` to 60; both are positive.
Wrong passwords return a fixed 401; invalid sessions, CSRF and rate limits use
existing auth errors. Linking failure at callback uses the fixed frontend error
redirect, preserving the existing session cookie without exposing private details.

## HTTP

| Endpoint | Behavior |
| --- | --- |
| `POST /api/v1/auth/google/link/start` | Re-authenticate a password account and initiate explicit Google linking. |
| `GET /api/v1/auth/google/start` | Start Google login with browser-bound state. |
| `GET /api/v1/auth/google/callback` | Verify Google identity and commit an ordinary session, then redirect. |
| `GET /api/health/live` | Always returns 200 while the API can serve requests. |
| `GET /api/health/ready` | Checks PostgreSQL, Redis and SeaweedFS; returns 200 or 503. |
| `GET /api/docs` | Interactive Swagger UI. |
| `GET /api/openapi.json` | Generated OpenAPI schema. |
| `GET /api/v1/auth/csrf` | Sets/reuses an HttpOnly CSRF cookie and returns its token. |
| `POST /api/v1/auth/register` | Creates an account/session and queues verification email after commit; returns 201 and a session cookie. |
| `POST /api/v1/auth/login` | Password login; returns user/session IDs and expiry, and sets a session cookie. |
| `POST /api/v1/auth/logout` | Revokes the current session, clears its cookie and returns 204. |
| `POST /api/v1/auth/logout-all` | Revokes the current user's sessions, clears the cookie and returns 204. |
| `GET /api/v1/auth/sessions` | Lists only the authenticated user's active sessions and public metadata. |
| `DELETE /api/v1/auth/sessions/{session_id}` | Revokes an owned session; returns 204 or a generic 404. |
| `POST /api/v1/auth/password/change` | Requires the current password; changes it, retains the current session and revokes others. |
| `POST /api/v1/auth/email-verification/request` | Requests verification mail for the authenticated user after token commit; returns 202 and retains the cookie. |
| `POST /api/v1/auth/email-verification/confirm` | Consumes a valid verification token and verifies its user's email; returns 204 without requiring login. |
| `POST /api/v1/auth/password-reset/confirm` | Changes the password, consumes a reset token, revokes owned sessions and clears the browser session cookie; returns 204 without requiring login. |
| `POST /api/v1/auth/password-reset/request` | Returns the same 202 for every account outcome; commits an eligible reset token before email queuing. |

Authentication POST and DELETE requests require an exact allowed `Origin` and matching
43-character URL-safe tokens in the CSRF cookie and `X-CSRF-Token` header, compared
in constant time. CSRF bootstrap rejects `Sec-Fetch-Site: cross-site` and reuses an
existing valid token. The JSON token enables header submission while the cookie
remains HttpOnly. Clients must include cookies. Production `__Host-` cookies also
prevent subdomains from injecting domain-scoped authentication cookies.

`RedisRateLimiter` uses an atomic INCR/EXPIRE Lua script for fixed request windows;
denied attempts do not extend expiry. Registration, login, email-verification confirmation and
password-reset request/confirmation use hashed ASGI peer addresses; password change and
email-verification requests use the user UUID. The limiter does not parse forwarded
headers itself. Configure trusted proxy handling at the server when deploying behind a proxy, or clients share the proxy's
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
Beat runs the same app with an empty periodic schedule. Other business jobs and
periodic tasks are not implemented. Redis does not hold authoritative user data.

The auth application owns an `EmailSender` port with `send_email_verification`
and `send_password_reset` methods. Both accept internal recipient/token data and
return no message content. Callers must commit token creation before sending.
`CeleryEmailSender` validates the recipient with existing email normalization and
the 43-character URL-safe token format, then queues `auth.send_email`. It refuses
disabled mode or Celery protocol 1, uses protocol 2 redacted `argsrepr`/`kwargsrepr`,
ignores results and disables automatic publication retries. Queue or validation
failures become a fixed `EmailDeliveryUnavailable` without exception chaining.
Queue acceptance does not guarantee delivery; there is no transactional outbox
or automatic recovery for a crash/failure between database commit and publication.
Registration, verification-request and reset-request transports call this adapter
after token creation commits.

The API lifespan owns a Celery producer configured from its supplied `REDIS_URL`,
using JSON/protocol 2, ignored results and three-second connection/socket limits.
It does not replace Celery's current app or import worker tasks, and is closed on
shutdown. `get_email_sender` supplies its adapter after checking delivery mode.

`workers/celery_app.py` includes `auth/infrastructure/email_tasks.py` so workers
register `auth.send_email`. This bound task redacts request representations before
validation, including malformed/direct/eager calls, checks delivery mode again,
validates the message and invokes the `EmailSender` boundary. Its result is `None`,
ignored, with no stored task errors. Settings, payload and sender failures become
a fixed error; task failures do not expose the original exception or token.
Email message DTOs use `SecretStr`, omit tokens from representations and mask them
in JSON serialization. Raw tokens are extracted only for transport/delivery.

The development `FakeEmailSender` keeps the latest 100 distinct messages per worker
process in memory. Duplicate messages within that window are ignored. This is
bounded inspection/test state, not durable delivery or cross-worker idempotency;
it disappears on restart and has no HTTP inbox. Neither fake messages nor token
contents are logged. The fake remains available for automated tests and development.

`SmtpEmailSender` implements the same port using Python's standard-library
`smtplib`, `ssl` and `email` modules. SMTP mode selects it in `auth.send_email`;
fake mode retains the process-local fake and disabled mode fails closed. Both
adapters reuse the validated `EmailMessage` recipient/token DTO. The producer
accepts fake or SMTP mode without changing task names, payloads or redaction.

The SMTP adapter creates a plain-text verification/reset message with a fixed
subject, sender, normalized recipient, Date and Message-ID. The raw single-use
token appears only in the private email body and existing trusted broker payload,
never in HTTP responses or logs. Messages describe the configured lifetime from
the original request. Configured verification links appear in plain-text and HTML
alternatives; the token is a fragment rather than a server-visible query string.
The frontend reads and removes it, obtains CSRF protection and calls the existing
POST confirmation API. GET previews do not confirm an address. The frontend does
not persist tokens or change confirmation rules. Without a configured URL,
verification emails remain token-only; password-reset email is always token-only.

Each job uses a new timeout-bounded SMTP connection, upgrades with STARTTLS before
authentication or uses implicit TLS, and verifies certificates and hostnames using
the default SSL context. STARTTLS failure never falls back to plaintext. Provider
errors, timeouts and rejected recipients become the fixed `EmailDeliveryUnavailable`
without exception chaining. SMTP debug output is never enabled. The worker keeps
ignored results and redacted task representations for both modes. SMTP acceptance
does not guarantee inbox delivery; downstream bounces are handled by the supplied
SMTP service. Automatic delivery retries, durable idempotency and an outbox are
not implemented; duplicate jobs can send the same token again but cannot bypass
single-use confirmation. Deployment requires an SMTP service and an authorized
sender; no particular external vendor is embedded in the architecture.

Celery JSON bodies temporarily carry raw one-time tokens through the trusted
Redis broker because the worker needs them for email delivery. Redacted task
headers hide tokens in normal Celery events/logs; they do not encrypt message
bodies. Protect broker access and do not log payloads. No raw tokens are written
to PostgreSQL or task results.

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

Password-change tests cover shared password policy, current-password bounds and
verification, generic credential errors, canonical retained-session ownership and
validity, and expiry after lock acquisition. PostgreSQL/Redis checks verify
credential timestamps, retention of the current token/cache, revocation and replay
rejection for other sessions, preservation of another user's sessions, no cache
deletion when there are no other sessions, and rollback/retry after cache failure.
Competing changes exercise user/session locks and password rechecking after the
first transaction commits or rolls back.

Password-change HTTP tests cover authenticated owner propagation, CSRF ordering,
per-user limits, secret-safe DTOs/validation/errors, no premature success on commit
failure, and current-cookie retention. PostgreSQL/Redis flows exercise the native
rate window, wrong-current-password and policy rejection, successful change,
revoked-session replay rejection, login with the new password, old-password
rejection, cache-failure rollback/retry and disabled-account rejection. Generated
rate keys and session cache entries are removed after the isolated tests.

Email-verification HTTP tests cover confirmation without login, cookie retention,
hashed peer limits without trusting forwarded headers, CSRF ordering, secret-safe
DTOs/validation/errors, positive rate settings and no success before commit.
PostgreSQL/Redis checks cover single use, expired/future/unknown/malformed/wrong-type
tokens, retention of existing sessions, preservation of prior verification and
disabled status, rollback/retry after a late user-update failure and native Redis
rate windows. The rate-window test owns a unique peer key and removes it afterward.

Password-reset HTTP tests cover confirmation without login, secret-safe DTOs and
validation, fixed errors, CSRF ordering, peer-address limits, positive rate
settings and cookie clearing only after commit. PostgreSQL/Redis flows exercise
successful reset, consumption/replay, revocation/cache invalidation/replay rejection
for owned sessions, preservation of another user's sessions, old/new password
login and rejection without side effects for invalid tokens, ineligible accounts
or weak passwords. Cache-failure rollback preserves the password, token, sessions
and cookie; confirmation succeeds on retry without login. Native Redis checks
verify the configured limit and window using a unique peer key removed afterward.

Email-delivery tests cover both message types, recipient normalization, explicit
fake/disabled modes, refusal of protocol 1, safe queue options, bounded fake
recording/deduplication, registration of the Celery task and ignored results.
Eager task execution checks fixed settings/validation/sender errors and redaction
of malformed jobs in Celery failure logs and tracebacks. With `AUTH_TEST_REDIS_URL`
set, the integration test publishes both message types through native Celery/Kombu,
reads them from a real Redis queue and executes the registered task against the
fake. A unique Redis key prefix isolates all broker state; the test acknowledges
messages and deletes its queue and prefixed keys afterward. Tests send no external
email and do not start a separate worker process. SMTP tests cover configuration,
both message types, STARTTLS/implicit TLS, certificate verification, authentication
ordering, no plaintext fallback and sanitized connection/authentication/delivery
failures. A loopback SMTP receiver exercises actual SMTP transmission without a
new dependency. With PostgreSQL/Redis enabled, an HTTP integration test registers,
resends, verifies and resets a password through a Celery in-memory broker and the
SMTP worker adapter, checking commit-before-delivery, token redaction, session
revocation, new-password login and replay rejection. The existing Redis broker
integration test continues to exercise native queue serialization and cleanup.

Reset-request HTTP tests cover cookie retention and requests without login,
identical acknowledgements, commit-before-queue ordering, no queuing on transaction
failure, disabled delivery before account lookup, safe queue-failure metadata,
CSRF/rate ordering, generic transport errors and producer lifecycle configuration.
PostgreSQL/Redis checks exercise eligible/unknown/disabled/passwordless/malformed
email outcomes, hashed token storage and lifetime, verification of committed state
through an independent database connection before sending, request-to-confirmation
and login with the new password, rejected session replay, queue-failure persistence
and retry, and the native configurable rate window. The HTTP flows use the injected
development fake; the separate email-delivery test exercises the actual Redis queue.

Registration HTTP tests cover commit-before-cookie/email ordering, safe public DTOs,
production cookie flags, bounded user agents, peer limits ignoring forwarded headers,
CSRF/rate protection, disabled email delivery, fixed errors and secret-safe queue
failure logs. PostgreSQL/Redis checks verify committed account/credential/session/
verification-token state through an independent connection before sending, hash-only
persistence, login before verification, confirmation and replay rejection, preservation
of duplicate password/Google-only/disabled accounts, complete rollback after a late
database failure, retained accounts/sessions after publication failure, and a native
Redis rate window. The HTTP tests inject the development fake; the separate delivery
tests exercise the actual Redis broker. Generated session/rate keys and temporary
schemas are removed after testing.

Verification-request tests cover locked canonical email selection, ineligible-user
no-ops, configurable lifetime, hidden delivery tokens, current-user propagation,
commit-before-queue ordering, cookie retention, authentication/CSRF/rate protection,
rejection of caller-supplied recipients, fixed errors and safe queue-failure logs.
PostgreSQL/Redis tests verify committed hashed tokens through an independent connection
before sending, preservation and single use of earlier tokens, confirmation followed
by verified-user no-op, isolation from other users, user-row locks, disabled-user
rejection, rollback/retry after insertion failure, retained tokens after queue failure,
and the native per-user rate window. HTTP flows inject the development fake; the
separate delivery tests cover the actual broker. Temporary schemas and generated
session/rate keys are cleaned up.

Google adapter tests use HTTPX MockTransport and generated in-memory RSA keys, never
real Google requests or committed keys. They cover authorization/form parameters,
claim/signature/algorithm rejection, required claims, both documented Google issuers,
nonce/PKCE input validation, unsafe discovery endpoints, malformed/oversized JSON,
fixed HTTP/transport errors without code retry, inappropriate or ambiguous keys,
key rotation and unknown-key rejection, public-cache freshness/expiry, safe logs,
partial/unsafe settings, local callbacks and disabled-provider no-I/O behavior.

Google account-resolution tests cover linked/new/disabled users, email collisions,
canonical-account preservation, failed verification, hashed sessions, late-write
rollback and retry, concurrent subject/email races, and the active-user lock.
They use isolated PostgreSQL schemas and generated Redis session keys to validate
ordinary session caching/revocation, with no provider network calls.

OAuth-state tests cover the S256 reference vector, hashed storage, redacted DTOs,
malformed callback/Redis inputs, fixed errors, outages and failed creation.
With `AUTH_TEST_REDIS_URL`, generated keys exercise native expiry, `SET NX`
collisions, wrong-browser preservation, replay rejection, simultaneous callbacks
and expiry/replacement between read and atomic deletion. Keys are cleaned up.

Google browser tests cover cookie flags, commit-before-cookie ordering, fixed
redirects, provider/Redis/database failures, duplicate/malformed queries, navigation
checks, rate limits, settings validation and access-log query redaction. Isolated
PostgreSQL/Redis tests use a fake provider to exercise account creation, replay,
email collisions, wrong browsers, consent denial, session validation and logout.

Explicit linking tests use isolated PostgreSQL schemas, generated Redis state and
fake Google identities. They exercise current-password/CSRF/schema/rate guards,
Strict-cookie rejection, Google-only rejection, preserved passwords/profiles,
Google login after linking, replay, logout, session switching, disabled users,
changed credentials, stale-cache revocation, expiry, competing owners, late-write
rollback and fresh retry. Concurrent users cannot reassign a Google subject.

The backend GitHub Actions job starts disposable PostgreSQL/pgvector and Redis
services and supplies `AUTH_TEST_DATABASE_URL` / `AUTH_TEST_REDIS_URL`. The regular
pytest command therefore runs native integration/concurrency checks rather than
skipping them. CI credentials belong only to the disposable test database; tests
still create/drop isolated schemas and clean generated Redis keys/queues. Google
calls remain fake or mocked.
