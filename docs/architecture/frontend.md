# Ukladen Frontend Foundation

Status: shell, mandatory registration completion, browser email verification, email/Google login and registration, safe automatic/explicit Google linking, email password recovery, academic-group selection and a weekly calendar with personal-event create/edit/delete are implemented. Other business UI remains not implemented.

`apps/web` uses Next.js App Router, React and strict TypeScript. The root layout
provides a TanStack Query client created once per mounted provider. The frontend
uses the query client for same-origin API reads and writes. Product text is Russian.

Approved A1 branding is implemented through `src/shared/brand.tsx`: the calendar/note
symbol and a text wordmark. Home, auth, group-selection and calendar navigation reuse
this component; desktop sign-in also displays the full logo image. Root metadata
provides browser/Apple touch icons. PNG sources and reuse instructions are in
[brand exports](../../assets/branding/README.md). Matching frontend copies are static
imports under `src/shared/assets/`, optimized by Next.js and included in standalone
and Docker output through the existing static-asset copy.

All frontend routes set CSP `frame-ancestors 'none'; base-uri 'self'; form-action 'self'`,
`X-Frame-Options: DENY` and `X-Content-Type-Options: nosniff`. This blocks external
framing and form/base destination replacement without disabling Next.js scripts.
The existing auth no-store/no-referrer/noindex policies remain. In Compose API
requests bypass Next.js through Traefik, so these are frontend response headers.

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
success, invalid/expired, rate-limit and temporary-failure states. Confirmation
requires the matching registration session. HTTP 401 explains how to use the
registration browser or sign in before reopening the email; it also offers mailbox
recovery for an unknown registration. Anonymous mail clicks cannot activate an
existing credential.

`/auth/reset-password` provides the email request and new-password forms. Login links
to the request page; a valid email fragment opens the confirmation form. Fragment
capture and removal happen once per mount, without an API mutation until explicit
submission. The token stays only in mounted memory. Both forms obtain fresh CSRF
protection and use the existing same-origin reset endpoints with cookies and Origin.
Request acknowledgements do not reveal account eligibility. Confirmation requires
matching passwords, handles server password-policy rejection, and clears the cached
session identity on success. Invalid/reused/expired links offer another request;
transient failures allow retry. Reloading returns to the request page, so the email
link must be reopened. Another fragment navigates to a fresh form. The page shares
verification's no-referrer/no-store/noindex policies and mutation-free GET previews.

`/auth/complete-registration` reads `/api/v1/auth/registration` using the current
cookie with no-store/no-referrer and a zero-lifetime query cache. It shows the missing
password form and/or email confirmation step. Matching passwords and the backend's
configured minimum are required; passwords clear on completion or identity changes.
Authoritative Google registration needs no second email. Third-party Google users
request our verification after password setup. Waiting sessions poll every five
seconds, refetch on focus and offer manual refresh, resend with a 60-second UI
cooldown and logout. A failed identity refresh unmounts the password form and discards
its secrets; retry mounts an empty form. Server rate limits remain authoritative. Completion navigates
to a fresh workspace; expired sessions return to sign-in.

`/auth/confirm-google-link` uses the shared fragment capture/privacy implementation
and requires an explicit confirmation click. It POSTs `/api/v1/auth/google/email/confirm`
with CSRF and the original HttpOnly browser binding. Success discards the token and
navigates to the workspace; invalid/expired/replayed/wrong-browser proofs fail safely.
GET/previews perform no linking. No password, email proof or provider token is stored
in local/session storage.

The root `/` page links to `/workspace` through “Открыть календарь”.

Login and registration offer `GoogleAuth`, using the existing server-side OIDC flow.
It requests a JSON start response, accepts only the Google authorization endpoint
and performs full-page navigation after the backend sets its binding cookie.
Provider credentials stay in backend configuration. Rate-limit/service/network errors
remain on the form and allow retry; browser-back navigation restores the button.
Profile menus expose explicit linking in a native modal dialog with current-password
confirmation and fresh CSRF protection. Closing it, session expiry or changing the
workspace identity discards its private form. Wrong-password errors preserve the
session; invalid-session responses remove the private workspace.
`/auth/error` has no-referrer/no-store/noindex policies and a retry button. The exact,
single `reason=account_linking_required` query selects a password-login/link form.
Its explicit submission authenticates the existing Ukladen account, then initiates
the existing password-confirmed linking API without requiring profile navigation
or entering the password twice. The exact `reason=google_email_confirmation_required`
marker instead explains the fresh mailbox challenge and same-browser requirement.
Unknown/repeated reasons show the generic recovery page. The reason contains no authority or identity data; credential and OAuth guards
remain server-side. Passwords clear before navigation and on restored browser history.
See [Google setup and verification](../development/google-auth.md).

`/workspace` provides email/password login and registration using the existing CSRF
and session-cookie contracts. Registration navigates to completion before loading
calendar/group data. Any business response with 403 `code=registration_incomplete`
discards the private workspace and redirects to completion; explicit Google linking
handles the same state. Password visibility lasts three seconds. After completed login,
users without an academic profile can choose to connect a BSUIR group or continue
without one. Group selection uses the existing group catalogue, group-context,
profile PATCH and schedule-sync endpoints. The calendar displays the authenticated
user's resolved week and supports personal-event create/edit/delete. Profile actions
open the group selector or revoke the current session. It does not implement tasks,
page editing or saved views.

The workspace checks `/api/v1/users/me` before mounting private data. Each authenticated
identity owns a separate query client and mounted forms; logout, session expiry and
identity changes discard that client and cancel its reads. Session revalidation hides
private content until identity is checked. No private data is persisted in browser storage.

Schedule refresh reads the stored source state before requesting work (the public
group-events response before a profile change, or the owner sync-status endpoint
before a retry). A group-events 404 means there is no stored source yet and uses
an empty `not_synced` baseline; other errors stop the save and remain visible.
Completion requires an advanced attempt/success timestamp for the
selected group, or completion of the attempt already running at that snapshot.
An old `ready` state is not a new success. Polling continues after the three-minute
waiting notice and recovers when the worker finishes. The queue response is acceptance
only; no upstream task identifier is invented.

The week grid covers 00:00–24:00 in a scrollable region, initially scrolled to 08:00.
Events are clipped into overlapping day segments, including continuations from the
previous week; opening a segment edits the original interval. Lane placement uses
the clipped intervals, and card height follows duration without a maximum cap.
The selected-day agenda includes continuations. Civil dates, navigation, labels and
`datetime-local` inputs use the resolved calendar timezone (the user profile supplies
the initial timezone). Browser timezone does not select the calendar date.
Day boundaries and durations follow actual instants: DST days can have 23/25 hours.
On clock-change weeks each day shows local clock/UTC-offset ticks and the shared
column shows elapsed hours from midnight. Repeated input times require an explicit
offset selection; nonexistent local times are rejected. Editing preserves the original
instant, including seconds, when its displayed local time is unchanged. These
conversions use platform `Intl`; no timezone dependency was added.

`src/app` contains routing and the shell. `src/shared` contains the query provider
and connection indicator. Feature/entity/widget directories will be introduced
with real UI slices rather than empty scaffolding.

Zustand and the FullCalendar core, React, daygrid, timegrid and interaction packages
are installed and locked. The current weekly calendar is rendered with React and CSS;
it uses backend-resolved events and does not implement drag-and-drop or availability
calculations. Permissions, schedule resolution and planning rules remain backend-owned.

## Target product responsibilities

Status: partially implemented. Future business UI adds independent pages, direct event
editing, optional organization, block documents and database/calendar views. Subjects
are optional navigation. Date labels and time reservations must be distinguishable.
AI UI exposes supporting sources, recommendations, exact proposals/confirmation and
explicit automatic-action permission management. Shared editing and formulas are deferred.

Follow [workspace requirements](../product/workspace.md) and resolve editor/collaboration
scope in [open decisions](../product/open-questions.md) before choosing UI contracts.
The current calendar does not introduce an editor library or database-view system.

## Current verification and runtime

ESLint uses Next.js's accessibility, React and TypeScript rules. `tsc --noEmit`
provides type checking. Playwright runs Chromium tests against the built frontend:
shell/connectivity success/failure, verification/reset link handling and workspace flows.
Workspace tests cover account isolation/session expiry, registration/login and optional
group onboarding, CSRF-protected personal CRUD, read-only official events, queued/fast
IIS imports and recovery, interval continuations, calendar timezones and DST inputs.
Verification
tests check one POST with cookies/CSRF/Origin, fragment/history cleanup, privacy
headers, invalid input, server/network failures and mutation-free GET previews.
Password-reset tests also cover matching passwords, duplicate-submit prevention,
policy correction, generic request acknowledgements, retry and opening another link.
Google tests cover login/registration, cookie binding, duplicate starts, recovery,
destination validation, explicit linking from desktop/mobile profiles, password/CSRF
guards, native dialog dismissal and private-state cleanup on expiry.
Continuation tests cover existing-account password confirmation, login before link
initiation, desktop/mobile UI, retries, duplicate submits and untrusted error markers.
Registration tests cover desktop/mobile password setup, mandatory verification,
resend, polling, identity/session changes, error recovery and email-proof privacy.
Browser tests mock API responses; backend tests cover real PostgreSQL/Redis/SMTP
flows. Compose health verification checks the real backend separately.

Rendering errors use App Router `error.tsx` and `global-error.tsx` fallbacks with
a retry action and fixed JSON browser diagnostics. Failed health checks and email
verification/reset requests log safe event/status metadata; their responses can
include the backend request ID. Error messages, stacks, URLs and token fragments
are omitted from these diagnostics. Browser logs remain local to DevTools; no
remote telemetry SDK is installed. See [logging](../development/logging.md).

ESLint 9 is retained because the installed Next.js React plugins fail with ESLint
10. TODO: upgrade lint tooling when those plugins support ESLint 10.

The Dockerfile builds Next.js standalone output and serves it as the non-root
`node` user. No extra UI framework, font download or bundling orchestrator is used.
`npm run build` includes static assets in that standalone output; `npm start` runs
the same standalone server used by Docker.
