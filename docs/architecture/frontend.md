# Ukladen Frontend Foundation

Status: shell and browser email verification implemented; other business UI is not implemented.

`apps/web` uses Next.js App Router, React and strict TypeScript. The root layout
provides a TanStack Query client created once per mounted provider. The shell uses
the query client for a same-origin `/api/health/live` connection indicator and
renders Russian product text with an explicit pre-launch message.

The only frontend route handler is `GET /health`, which returns `{ "status": "ok" }`.
It checks the frontend process, not the backend. In Compose, Traefik routes API
requests directly to FastAPI. For local development, Next.js rewrites `/api/*` to
`BACKEND_URL`, defaulting to `http://localhost:8000`. This URL is captured during
the production build; the Docker build defaults it to `http://api:8000`.

`/auth/verify-email` is a dynamic page for email links carrying a token in the URL
fragment. Its client reads and validates the single token, removes the fragment
from browser history, obtains `/api/v1/auth/csrf`, then calls the existing same-origin
POST `/api/v1/auth/email-verification/confirm` with cookies and the CSRF header.
The browser supplies Origin; FastAPI retains all validation, expiry and single-use
business rules. A reused promise avoids duplicate confirmation when React repeats
effects. The page uses no-referrer/no-store/noindex policies and does not retain
tokens in browser storage. GET previews do not mutate user data. It renders Russian
success, invalid/expired, rate-limit and temporary-failure states. Login, registration
and password-reset UI are not implemented.

`src/app` contains routing and the shell. `src/shared` contains the query provider
and connection indicator. Feature/entity/widget directories will be introduced
with real UI slices rather than empty scaffolding.

Zustand and the FullCalendar core, React, daygrid, timegrid and interaction packages
are installed and locked. No Zustand store or calendar view is implemented.
Permissions, schedule resolution and planning rules are not implemented in the
frontend.

## Target product responsibilities

Status: not implemented. Future business UI presents independent pages, direct event
editing, optional organization, block documents and database/calendar views. Subjects
are optional navigation. Date labels and time reservations must be distinguishable.
AI UI exposes supporting sources and exact proposals/confirmation.

Follow [workspace requirements](../product/workspace.md) and resolve editor/collaboration
scope in [open decisions](../product/open-questions.md) before choosing UI contracts.
This documentation task introduces no editor library, layout or business UI.

## Current verification and runtime

ESLint uses Next.js's accessibility, React and TypeScript rules. `tsc --noEmit`
provides type checking. Playwright runs Chromium tests against the built frontend:
shell/connectivity success/failure and verification link handling. Verification
tests check one POST with cookies/CSRF/Origin, fragment/history cleanup, privacy
headers, invalid input, server/network failures and mutation-free GET previews.
Browser tests mock API responses; backend tests cover real PostgreSQL/Redis/SMTP
flows. Compose health verification checks the real backend separately.

Rendering errors use App Router `error.tsx` and `global-error.tsx` fallbacks with
a retry action and fixed JSON browser diagnostics. Failed health checks and email
verification requests log safe event/status metadata; verification responses can
include the backend request ID. Error messages, stacks, URLs and token fragments
are omitted from these diagnostics. Browser logs remain local to DevTools; no
remote telemetry SDK is installed. See [logging](../development/logging.md).

ESLint 9 is retained because the installed Next.js React plugins fail with ESLint
10. TODO: upgrade lint tooling when those plugins support ESLint 10.

The Dockerfile builds Next.js standalone output and serves it as the non-root
`node` user. No extra UI framework, font download or bundling orchestrator is used.
`npm run build` includes static assets in that standalone output; `npm start` runs
the same standalone server used by Docker.
