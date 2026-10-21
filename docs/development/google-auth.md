# Google sign-in and account linking

Status: implemented. Google OIDC uses the backend's opaque sessions, browser-bound
single-use state, nonce and S256 PKCE. No Google client secret or provider tokens
are stored in frontend code or browser storage. Registration completion follows
[ADR 0008](../adr/0008-require-completed-registration.md). No new dependency is required.

## Configuration

Use a Google OAuth client of type **Web application**. Register each exact callback
that will be used in Google Auth Platform / Clients / Authorized redirect URIs:

- Local Compose: `http://localhost:8080/api/v1/auth/google/callback`.
- Home server: `https://ukladen.app/api/v1/auth/google/callback`.

The scheme, hostname, port, path and trailing slash must match. Native backend
development must use the callback registered for that browser's actual origin.
The existing `openid email` scopes request identity only, not Gmail, Drive or Calendar data.

Keep the real client ID and secret in ignored private env files. Local settings:

```dotenv
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8080/api/v1/auth/google/callback
FRONTEND_AUTH_SUCCESS_URL=http://localhost:8080/workspace
FRONTEND_AUTH_ERROR_URL=http://localhost:8080/auth/error
```

Home `.env.home` uses the same credentials with these public destinations:

```dotenv
GOOGLE_REDIRECT_URI=https://ukladen.app/api/v1/auth/google/callback
FRONTEND_AUTH_SUCCESS_URL=https://ukladen.app/workspace
FRONTEND_AUTH_ERROR_URL=https://ukladen.app/auth/error
```

All three Google settings and both frontend destinations are needed. Production
uses Secure `__Host-` cookies, SameSite=Lax and the allowed HTTPS origin. Local
HTTP uses the unprefixed cookie names and allowed origins in `.env.example`.
Use a private env file matching the actual launch configuration: the base Compose
services read `.env`; the home override reads `.env.home`. Supplying only
`--env-file .env.home` does not replace the base services' `env_file` setting.
Rebuild API/web after code changes and recreate the API after credential changes.
Switching to the home override also changes network exposure; follow the
[home deployment guide](../deployment/home-server.md) deliberately.

## Browser flows

The Google button on login and registration works without filling password fields.
It requests `GET /api/v1/auth/google/start` with `Accept: application/json`, receives
the authorization URL and browser-binding cookie, then navigates to Google.
Ordinary browser/API navigation without that explicit header retains the original
303 response. The backend checks navigation origin, state, nonce, PKCE, signed
identity claims and account eligibility before committing the session. Success
redirects to `/workspace`; cancellation or callback failure redirects to `/auth/error`.
That page offers retry and password sign-in without exposing provider error data.
Initial rate-limit, network and service errors stay on the current form for retry.

Application access requires an active account, verified canonical email and an
Ukladen password. A successful authentication may issue a restricted registration
session; `/workspace` redirects it to `/auth/complete-registration` before displaying
private data. The backend enforces the same rule on every protected business API,
including cached sessions. This applies to existing sessions and accounts too.

| Google sign-in case | Result |
| --- | --- |
| Previously linked subject | Authenticate that account; complete missing email proof/password before application access. |
| New Gmail or validated Workspace identity, unused email | Create the account with verified email; require an Ukladen password, without another email. |
| New third-party Google email, unused email | Create a restricted account; require an Ukladen password and our own email confirmation. |
| Unlinked Gmail/Workspace identity, matching active verified account, no prior Google identity | Attach to that account and sign in automatically; preserve password and profile. |
| Unlinked third-party Google email, matching active verified password account, no prior Google identity | Send a fresh mailbox challenge; attach and sign in only after confirmation in the original browser. |
| Matching unverified/disabled account, or another Google identity already attached | Do not merge or overwrite; offer password sign-in, completion/recovery or explicit profile linking. |

Authority comes from the validated signed ID token: `@gmail.com`, or boolean true
`email_verified` with a valid `hd` hosted-domain claim. A Google account registered
with an external mailbox and no hosted-domain claim needs fresh mailbox proof;
`email_verified` alone is insufficient. See Google's
[server-side verification guidance](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token).
Subject remains the external identity key. Matching uses the normalized canonical
email; Gmail dot/plus aliases are not merged. Identities never transfer between users.

`GET /api/v1/auth/registration` returns only the current session owner's email,
verification/password requirements and password minimum. The completion page polls
while waiting for verification, supports bounded resend and logout, and accepts
matching passwords through `POST /api/v1/auth/registration/password`. This creates
only a missing credential, revokes other sessions and cannot overwrite a password.
Email/password registration supports ordinary email providers, independently of
Google. Our email-confirmation endpoint requires an active session for that same
account, including its restricted registration session. Use the registration browser,
or sign in to the same account before reopening the link. An anonymous/other-account
mail click cannot activate a registration created by a third party; use password
recovery for an unknown registration. Reset/change invalidates earlier reset links.

Pending sessions get HTTP 403 with `code=registration_incomplete` from business APIs;
their cookie stays available for completion. Expired sessions receive HTTP 401.

For first linking of a third-party Google mailbox, the callback commits a hashed,
single-use challenge before queuing email. It redirects to the fixed marker
`?reason=google_email_confirmation_required`. The email opens
`/auth/confirm-google-link#token=...`; the user explicitly confirms and the page POSTs
to `/api/v1/auth/google/email/confirm` with CSRF protection. Opening/previewing the
page cannot link an account. The token is removed from the address bar and kept only
in mounted memory. The challenge lasts `AUTH_OAUTH_STATE_TTL_SECONDS` (600 by default)
and requires the original HttpOnly OAuth browser cookie, unchanged canonical email
and password, and an active account. Replays and wrong browsers fail without linking.

The `?reason=account_linking_required` page retains **Войти и связать Google** as a
fallback. It authenticates the existing Ukladen password account, then starts a fresh
explicit Google flow. An incomplete account is first redirected to registration
completion. Query markers contain no authority, identity, code or state.

Signed-in users can choose **Связать с Google** in the profile menu. The modal requires
the current password and fresh CSRF protection. The callback checks the original
active session and unchanged password. A first link to a third-party Google mailbox
also needs the email challenge, bound to that original session. Password, profile
and canonical email are preserved even when the explicitly selected Google email
differs. Closing the form or changing sessions discards its password. Passwordless
legacy Google users must first complete password setup. Unlinking remains unimplemented.

If someone registered an unverified account with your email, password recovery proves
mailbox ownership, sets your password, verifies the email and revokes all old sessions.
It also removes external identities attached while that account was unverified.
Previously verified accounts retain their linked identities during password recovery.

## Upgrade and runtime

Apply Alembic `0021_google_email_confirmations` before starting the updated API.
It adds a separate challenge table, without storing provider tokens. Rebuild/recreate
API, web and the existing Celery worker together: the worker must recognize the new
`google_link` email kind. No new env settings or secrets are required. Security fixes after this migration
also require the matching registration session for ordinary email confirmation under
[ADR 0008](../adr/0008-require-completed-registration.md#security-amendment--2026-10-17).
The existing SMTP settings and `AUTH_EMAIL_VERIFICATION_URL` supply delivery and the frontend origin.
Disabled/fake delivery cannot deliver real mailbox challenges; trusted Google login
itself does not require SMTP.

The migration conservatively rechecks legacy passwordless, non-Gmail Google accounts
whose verification timestamp came directly from initial identity creation and which
have no consumed Ukladen verification token. It preserves the account and all data;
a fresh authoritative Workspace callback can prove ownership, otherwise use email
confirmation/recovery. The downgrade drops the challenge table and does not restore
unproven email ownership. Existing unverified users need verification; existing
passwordless users need a password. Deployment does not delete accounts.

## Troubleshooting

- `redirect_uri_mismatch`: add the exact configured callback to the same Google
  OAuth client's authorized redirect list, then start a fresh flow.
- `invalid_client` / `deleted_client`: check the client ID/secret pair and that the
  client still exists and is a web client; recreate the API after updating its env file.
- Google testing/audience restrictions: check the project's Audience configuration
  and which users can authorize it. Organization-only clients cannot accept outsiders.
- `disallowed_useragent`: retry in a normal supported browser instead of an embedded view.
- `/auth/error?reason=google_email_confirmation_required`: check the Google mailbox
  and open the fresh link in the same browser before expiry. Starting another Google
  flow replaces its browser binding; request a fresh challenge if needed.
- `/auth/error?reason=account_linking_required`: the account is ineligible for safe
  automatic linking. Use Ukladen sign-in/completion or recovery, then explicit linking.
- A generic `/auth/error`: retry with fresh state and cookies on the original hostname.
  Inspect safe API diagnostics for provider, state or database failures; never copy
  callback query strings or credentials into logs or support messages.
- A 503 before Google opens: confirm all five settings are loaded in the running
  API and that Redis and Google's discovery/JWKS endpoints are reachable.
- A 429: wait for the rate-limit window before trying again. No protection is disabled.

The API writes structured JSON to container stderr, not to a project log file.
Inspect the running backend with:

```bash
docker compose logs --since 15m api
docker compose logs -f --tail 100 api
docker compose logs --since 15m api | rg 'auth.google_callback_rejected'
```

Look at `event`, `error_type` and `request_id`. `AccountLinkingRequired` means the
Google identity passed validation, but the existing account is ineligible for
safe automatic linking (for example, unverified or already linked to another subject). `InvalidOAuthState` means the browser binding, single-use state or expiry
check failed. `ExternalIdentityUnavailable` indicates provider configuration or
communication failure. See [logging](logging.md) for home-stack options and safe
diagnostic fields. Do not enable raw HTTP, token or cookie dumps.

References: [Google OIDC](https://developers.google.com/identity/openid-connect/openid-connect),
[OAuth web-server errors](https://developers.google.com/identity/protocols/oauth2/web-server#authorization-errors).
The button uses Google's official [G asset](https://developers.google.com/static/identity/images/g-logo.png)
and follows the light button direction from the
[branding guide](https://developers.google.com/identity/branding-guidelines).

## Verification — 2026-10-16

- Backend Ruff, formatting and Pyright passed. The authentication group had
  **635 passing tests**, including real disposable PostgreSQL/Redis and loopback SMTP,
  with 154 dependency deprecation warnings. Both JSON and legacy 303 starts are covered;
  linking covers real account/session persistence with mocked provider identities.
- Frontend lint, typecheck, production build and **73 browser tests passed**, including
  17 Google cases for starts, redirect validation, linking, error recovery and session
  privacy. Browser tests use mocked API responses and a stub Google destination.
- Private `.env` credentials were copied into `.env.home` without printing or committing
  them. Home callback/success/error destinations were configured for `ukladen.app`.
  A malformed local `SCHEDULE_SYNC_INTERVAL_SECONDS` value was repaired during validation.
- Both resolved configurations validate. Base/home Compose validation and the home
  exposure, secret-isolation and proxy-trust checker passed.
- Real Google discovery and authorization requests for both registered callbacks reached
  Google's sign-in page (HTTP 200), without `redirect_uri_mismatch` or `invalid_client`.
  This confirms the authorization-start configuration; it does not establish a real
  user's completed consent, client-secret exchange or Ukladen session.
- At the owner's request, only the local base Compose API/web were rebuilt and
  recreated. Both are healthy; their existing network and local ports were retained.
  The home deployment was not activated. The running API's five Google/frontend
  settings match `.env`. Local health/readiness and workspace requests returned 200.
- On `http://localhost:8080`, the real JSON start returned the expected Google
  destination and HttpOnly/SameSite=Lax binding cookie; the legacy start returned 303.
  A browser-bound cancellation redirected to the configured error page, whose privacy
  headers were present, and left the client unauthenticated. The visible login button
  opened Google's actual **Sign in to continue to Ukladen** screen. That browser was
  unauthenticated; completing account sign-in was handed to the owner.

The full non-auth backend suite was not rerun for this auth-only slice. Actual Google
account selection/consent requires an authenticated user browser; automated tests use
mocked Google identities and never weaken signature, cookie or state checks.

## Login continuation verification — 2026-10-16

- Backend Ruff, formatting and Pyright passed; the auth group again had **635 passing
  tests** with 154 dependency deprecation warnings. Real disposable PostgreSQL/Redis
  tests now cover the initial collision, no premature identity/session creation,
  password login, fresh explicit linking, replay rejection and later Google login
  on the original account. User data and password credentials are preserved.
- Frontend lint, typecheck, production build and **83 browser tests passed**, including
  ten added cases for desktop/mobile continuation, password failure/retry, link-service
  failure, privacy, duplicate submissions, browser back and untrusted reason queries.
- Local/home Compose configuration validation passed. Only local API/web were rebuilt
  for the owner's selected local stack; the home profile was not activated.
  Both containers are healthy on their existing network. Local health/readiness and
  the new continuation page returned 200; privacy headers and the rendered form were
  checked on `localhost:8080`, including visual browser inspection.
- Owner-initiated live Google callbacks reached `AccountLinkingRequired` after provider
  exchange and identity validation. This established the previous failure category;
  it did not complete account linking. The new password-confirmed flow still requires
  the owner to enter their credentials and complete Google selection in their browser.

The full non-auth backend suite was not rerun for this continuation slice.


## Completed registration verification — 2026-10-16

- Ruff lint and formatting, Pyright and the full backend suite passed:
  **1498 tests**, with 653 dependency deprecation warnings. Disposable PostgreSQL,
  Redis and SeaweedFS were enabled; user/application storage was not used by tests.
- Coverage includes the global business-API registration gate, cached sessions,
  authoritative/untrusted Google email decisions, verified-account automatic linking,
  browser-bound mailbox proof, replay/expiry/password/session changes, safe recovery
  of unverified accounts and conservative legacy migration upgrade/downgrade.
  All three email kinds pass queue serialization, worker dispatch and redaction checks;
  the new Google message also checks the private fragment URL and OAuth lifetime.
- Frontend lint, typecheck, production build and **98 browser tests passed**.
  Added cases cover desktop/mobile password setup, email gating/resend, completion
  polling, account/session changes, error recovery and explicit Google mail confirmation.
  Browser APIs and Google destinations are mocked; backend provider claims are
  validated with generated signing keys and mocked provider responses.
- Base and home Compose configurations validate. Only the selected local base API,
  web and email worker were rebuilt/recreated; migration `0021_google_email_confirmations`
  was applied before startup. All three services are healthy. The existing local
  ports/network and account data were retained; the home profile was not activated.
- Live local checks passed for health/readiness, workspace/new auth pages, privacy
  headers, anonymous denial, Google JSON start/browser-cookie flags and safe
  cancellation. Both fixed recovery reasons render their intended screens. The
  completion and mailbox-challenge pages were visually inspected in the browser.
- The configured SMTP service accepted a TLS connection and authentication. The
  probe sent no email; real recipient inbox delivery was not checked in this slice.
  No new secret, env setting or dependency is needed. Temporary test containers were
  stopped after verification.

The final owner Google account selection/consent and real inbox confirmation still
require the owner's browser. This record does not claim a completed human Google
sign-in; no signature, state, browser-binding, CSRF or email-proof guard was weakened.


## Security follow-up — 2026-10-17

The matching-session email confirmation requirement, stale reset-link revocation,
per-email throttling and frontend security headers are implemented. The final full
backend suite passed 1509 tests; frontend lint/typecheck/build and 101 browser tests
passed. The registration API still returns 409 for an already registered address,
revealing registration existence; password-login errors and reset-request
acknowledgements remain generic. Eliminating that signal requires a signup-contract
change. Live Google consent and external inbox delivery were not verified in that run.
Earlier verification records above describe their own implementations and runs.
