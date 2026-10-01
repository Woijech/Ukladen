# Ukladen Frontend Foundation

Status: shell implemented; business UI is not implemented.

`apps/web` uses Next.js App Router, React and strict TypeScript. The root layout
provides a TanStack Query client created once per mounted provider. The shell uses
the query client for a same-origin `/api/health/live` connection indicator and
renders Russian product text with an explicit pre-launch message.

The only frontend route handler is `GET /health`, which returns `{ "status": "ok" }`.
It checks the frontend process, not the backend. In Compose, Traefik routes API
requests directly to FastAPI. For local development, Next.js rewrites `/api/*` to
`BACKEND_URL`, defaulting to `http://localhost:8000`. This URL is captured during
the production build; the Docker build defaults it to `http://api:8000`.

`src/app` contains routing and the shell. `src/shared` contains the query provider
and connection indicator. Feature/entity/widget directories will be introduced
with real UI slices rather than empty scaffolding.

Zustand and the FullCalendar core, React, daygrid, timegrid and interaction packages
are installed and locked. No Zustand store or calendar view is implemented.
Permissions, schedule resolution and planning rules are not implemented in the
frontend.

ESLint uses Next.js's accessibility, React and TypeScript rules. `tsc --noEmit`
provides type checking. Playwright runs two Chromium smoke tests against the built
frontend: shell/connectivity success and API failure. Browser tests mock the API
probe; Compose health verification checks the real backend separately.

ESLint 9 is retained because the installed Next.js React plugins fail with ESLint
10. TODO: upgrade lint tooling when those plugins support ESLint 10.

The Dockerfile builds Next.js standalone output and serves it as the non-root
`node` user. No extra UI framework, font download or bundling orchestrator is used.
`npm run build` includes static assets in that standalone output; `npm start` runs
the same standalone server used by Docker.
