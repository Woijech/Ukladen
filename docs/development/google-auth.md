# Google sign-in and account linking

Status: implemented. Google OIDC uses the backend's opaque sessions, browser-bound
single-use state, nonce and S256 PKCE. No Google client secret or provider tokens
are stored in frontend code or browser storage. No new dependency or migration was added.

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

A verified Google identity creates a new account only when its email is unused.
An existing password account is never merged automatically based on an email match.
Sign in with its password, open the profile menu and choose **Связать с Google**.
The modal requires the current Ukladen password, obtains fresh CSRF protection and
POSTs to `/api/v1/auth/google/link/start` with the same JSON response option.
Select the Google account to link. The callback requires the original active session
and unchanged password. Existing password/profile data is preserved, and later Google
login resolves the linked account. An identity owned by another account cannot transfer.
Passwordless Google-only accounts cannot use this password-confirmed linking flow.

Modal dismissal, session expiry and identity changes discard the password form.
Wrong-password failures preserve the session; invalid-session failures return to sign-in.
Browser diagnostics record only stage/status and a validated request ID, never URLs,
provider responses, tokens, email or passwords.

## Troubleshooting

- `redirect_uri_mismatch`: add the exact configured callback to the same Google
  OAuth client's authorized redirect list, then start a fresh flow.
- `invalid_client` / `deleted_client`: check the client ID/secret pair and that the
  client still exists and is a web client; recreate the API after updating its env file.
- Google testing/audience restrictions: check the project's Audience configuration
  and which users can authorize it. Organization-only clients cannot accept outsiders.
- `disallowed_useragent`: retry in a normal supported browser instead of an embedded view.
- A successful Google step followed by `/auth/error`: retry with fresh state and
  cookies on the original hostname. For a pre-existing email, use explicit linking.
  Inspect safe API diagnostics for provider, state or database failures; never copy
  callback query strings or credentials into logs or support messages.
- A 503 before Google opens: confirm all five settings are loaded in the running
  API and that Redis and Google's discovery/JWKS endpoints are reachable.
- A 429: wait for the rate-limit window before trying again. No protection is disabled.

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
