# Authentication security review — 2026-10-17

Scope: email/password registration and login, registration completion, mailbox
verification, password recovery/change, browser sessions, Google login/linking,
CSRF, throttling, frontend privacy/framing and runtime dependency advisories.
This is a source review and regression check, not a claim that the application
or deployment has no vulnerabilities.

## Reproduced issues and fixes

| Priority | Issue | Implemented correction |
| --- | --- | --- |
| P1 | An anonymous mailbox click could activate a registration with credentials supplied by someone else. | Verification requires an active registration session for the token's owner. Anonymous confirmation returns 401; a different user gets a generic 400, without consuming the token. Unknown registrations use mailbox recovery, replacing the password and revoking old sessions/identities. |
| P1 | A second unused reset link could change the password again after a successful reset or password change. | Both password operations invalidate all outstanding reset tokens in the same transaction. User-first locking serializes competing sibling links without a token/user lock cycle. Rollback preserves tokens and credentials for retry. |
| P2 | Changing client addresses bypassed per-address password-guessing and reset-mail limits. | Login and reset requests enforce independent peer and normalized-email limits in Redis, using the existing configured threshold/window. Keys contain hashes rather than literal emails. |
| P2 | Authentication pages allowed external framing. | Frontend CSP denies all frame ancestors and restricts base/form destinations to self. Legacy X-Frame-Options denies framing; nosniff protects response MIME handling. |
| P2 | A failed identity refresh left the earlier password form mounted. | Registration hides/unmounts that form on refresh failure, discards its secrets and mounts an empty form after a successful retry. |

The first four regression cases failed against the previous implementation. Regular
non-Google email registration, confirmation and password login already worked;
regressions now explicitly cover Outlook, Yandex and Proton addresses with real
PostgreSQL/Redis and a fake mail sender. These tests send no email to those domains.

The security amendment to [ADR 0008](../adr/0008-require-completed-registration.md)
records the verification-session requirement. The request body remains token-only;
anonymous verification clients must authenticate to the same account before retrying.
The browser explains how to reopen the link after sign-in and offers password recovery.
Reset confirmation remains available without login, authorized by its mailbox token.
No migration, new project dependency, secret or additional env setting is required.
Eight configured secret values from the private local/home files were compared
against 30 generated public frontend assets without printing the values; no matches
were found. The running frontend container does not receive the backend's Google,
SMTP, database, object-storage or tunnel secrets. Private env files are untracked and have no entries in repository history.

## Existing protections reviewed

- Opaque random HttpOnly sessions, hash-only database tokens, expiry, owner-scoped
  session management and revocation/cache invalidation on reset/logout.
- Argon2id credentials, bounded password inputs, generic password-login failures
  and a dummy hash for unknown users. No passwords or tokens in browser storage.
- Exact allowed Origin plus double-submit CSRF for mutations. Forwarded addresses
  are not parsed by application limiters; proxy trust remains deployment-owned.
- Canonical active-user and registration-readiness checks before business APIs,
  including cached sessions. Caller-supplied user IDs cannot authorize operations.
- Google signature/issuer/audience/nonce/expiry/email claims, PKCE, single-use state
  and browser binding. Subjects cannot transfer between users; automatic linking
  requires authoritative Google email and an already verified matching account.
- External Google mailbox links recheck browser, canonical email, credential
  fingerprint and original session when applicable. Provider tokens are not stored.
- Private fragments, no-referrer/no-store auth pages and safe diagnostics. SMTP
  uses TLS and sanitized errors; queue acceptance is not an inbox-delivery guarantee.

## Dependency findings and limits

`pip-audit` found no known advisories in the locked Python runtime requirements.
`npm audit --omit=dev` reported zero runtime advisories. The generated Next.js
standalone tree contains no braces/micromatch/fast-glob package directories.

The full development audit reports five affected dependency entries caused by one
unpatched [braces advisory, GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm)
in the Next.js ESLint toolchain. It processes repository glob patterns, not website
requests. The proposed automatic fix downgrades eslint-config-next from major 16 to
14 and is unsuitable for this stack. No downgrade, audit suppression or unreviewed
vendor patch was applied. A compatible upstream fix remains unavailable at review.

The existing registration contract still returns 409 for an already registered
address. This reveals registration existence and is an explicit residual privacy
tradeoff; it does not expose credentials or authorize account access. Eliminating
that signal requires redesigning immediate registration sessions and the signup
response contract, beyond a compatible security fix. Password-login failures and
reset-request acknowledgements remain generic.

Review excludes real account consent, external recipient inboxes, compromised
mailboxes/devices, infrastructure penetration testing and distributed load testing.
The local base stack uses loopback HTTP development settings. The running Traefik
container is on `ukladen_default`; the leftover tunnel is isolated on `ukladen_edge`,
so that tunnel is not connected to the local proxy. Deployment must use
the HTTPS/Secure-cookie home configuration and trusted proxy settings in the
[deployment guide](../deployment/home-server.md).

## Verification

Status: completed.

- Ruff lint/format and Pyright passed. The final sequential backend run passed
  **1509 tests** with 664 dependency deprecation warnings and no failures or skips.
  Real disposable PostgreSQL, Redis and SeaweedFS were enabled, including concurrency,
  rollback, SMTP loopback, malformed-token and owner-isolation checks.
- Frontend lint, typecheck and production build passed; **101 browser tests passed**.
  Coverage includes the new sign-in-required verification state, private form cleanup,
  security headers and existing password/Google/session recovery scenarios.
- `pip-audit` passed for locked runtime requirements; npm runtime audit passed with
  zero advisories. The development-only braces finding remains as described above.
- Base/home Compose configurations validated. Only the selected local base API/web
  were rebuilt and recreated; both are healthy. No schema migration or env edits
  were needed, no test users were created in application storage, and no real emails
  were sent. The home profile was not activated.
- Live local checks passed for health/readiness, all six auth/workspace page header
  policies, anonymous verification rejection, cross-origin login rejection, generic
  bad-credential rejection, and Google start/cancellation with PKCE and browser binding.
  The required-session page was visually inspected with a synthetic fragment.
- Temporary test containers were stopped after validation. Two earlier overlapping
  test processes collided while creating PostgreSQL's shared vector extension;
  the final full run used one process. Run test processes sequentially against a
  shared test database, even when their schemas are isolated.

Earlier dated verification in other guides remains historical. Actual Google consent
and external inbox delivery were not exercised with an owner's account in this review.

References used for review: [OWASP authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html),
[password recovery](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html),
and [CSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).
