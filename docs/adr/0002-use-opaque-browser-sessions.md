# ADR 0002: Use Opaque Browser Sessions

Date: 2026-10-01
Status: accepted by the repository owner.
Runtime authentication status: implemented; see [backend architecture](../architecture/backend.md).

## Context

The primary architecture listed access/refresh tokens, while the authentication
specification requires opaque server-side sessions for browser authentication.
The repository owner approved aligning the architecture with that specification.

## Decision

Use a cryptographically random opaque session token in an HttpOnly cookie.
Persist only SHA-256(token), never the raw session token. PostgreSQL is the
canonical session store; Redis caches session data and remains disposable.
Session validation checks the token hash against Redis with a PostgreSQL fallback.

Production cookies use Secure, SameSite=Lax and Path=/, with the preferred name
`__Host-ukladen_session` and no Domain attribute. Cookie-based mutations require
CSRF token/header protection in addition to SameSite.

Google OIDC verifies external identity, then creates a normal Ukladen session.
Google tokens do not become Ukladen sessions. JWT access/refresh tokens and mobile
bearer-token authentication are outside the initial browser authentication scope.

## Consequences

Session expiry and revocation belong to the backend. Revocation must invalidate
cached sessions so Redis cannot continue authenticating a revoked session.
Backend replicas share PostgreSQL and Redis rather than process-local session state.

The original decision recorded the design only. Subsequent implementation added
endpoints, persistence, configuration and tests following
[AUTH_SPEC.md](../modules/auth/AUTH_SPEC.md).
