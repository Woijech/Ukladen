# Ukladen Frontend

Status: implemented — shared light/dark shell, authentication and registration completion, optional group selection, day/week personal calendar, tasks with subtasks/trash, page/block editor, materials, collections/tags, database table/calendar views, search, reminders/inbox and profile/avatar settings, plus the locally implemented AI-04 chat/settings/usage UI. AI activation remains pending. The boundaries below distinguish these interfaces from future backend capabilities.

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
open the group selector, settings or revoke the current session. The AI section
uses the default-disabled AI backend and explains missing activation/configuration. Official event details are
read-only; override editing and saved event-calendar views remain API-only.

Tasks use the same desktop/mobile navigation, shared API client, per-identity
query cache and native dialogs as the other workspace sections. The paginated
list supports status/priority filters, detail/edit forms, exact deadlines/effort,
arbitrary-depth subtasks and parent moves. Branch trash requires confirmation;
only a trash-batch root can restore its batch, preserving earlier independent
deletions. The backend validates hierarchy and optimistic versions. Version
conflicts retain the editor draft until explicit reload. Deadline input uses
the profile timezone and explicit DST disambiguation. Task surfaces consume the
shared light/dark tokens. AI-10 adds dependencies/page links, explicit remainder,
weekly work settings, deterministic plan previews/partial acceptance and manual
session checks/pin/move/cancel controls. Calendar task sessions and opt-in
nonblocking deadlines use a separate projection; hiding them changes no busy
calculations. Extracted AI tasks can be edited into a new immutable preview before
confirmation. Task/deadline reminders remain not implemented. See
[task planning](../development/task-planning.md) and [task contracts](../development/tasks.md).

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

The day/week grid covers 00:00–24:00 in a scrollable region, initially scrolled to 08:00.
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

## Design system and structure

The A1 calendar/note symbol remains the product identity. `src/app/globals.css`
defines semantic CSS variables for surfaces, plum text, lavender accent, borders,
muted text, focus rings, destructive feedback and official-event teal. Components
consume these tokens rather than inventing page palettes. `data-theme` selects
light/dark/system; a small startup script prevents an incorrect initial theme.
Only `ukladen-theme` is persisted locally. System mode follows the OS, and
`prefers-reduced-motion` suppresses decorative transitions. System fonts avoid
network font downloads. Use the existing spacing, radii, button and field classes.

- `src/shared/api.ts`: same-origin cookie requests, fresh CSRF for writes, typed
  errors and global session-expiry/registration-completion handling.
- `src/shared/ui.tsx`: native dialog with Escape, focus containment/return and
  backdrop dismissal; empty/loading/error/retry states, pagination and duplicate
  submission protection with inline accessible action feedback.
- `src/shared/theme.tsx`: theme control and external-store subscription.
- `src/app/workspace/workspace.tsx`: session boundary, group/sync flow, sidebar,
  topbar and original event renderer/forms. `navigation.tsx` owns section labels
  and the inline SVG icon set. Section navigation stays inside `/workspace`.
- `workspace/views.tsx`: dashboard, settings and section composition. The workspace
  views, note editor and database editor load lazily. Panels under `workspace/panels`
  own content forms, resources, organization and optional relations.
- `workspace/workspace.css`: shared workspace and panel layout. Reuse its panels,
  toolbar, form, list, action and confirmation patterns before adding variants.

The sidebar initially exposes Calendar, Notes and Tasks; More reveals the existing
secondary sections (dashboard, materials, databases, organization, search, inbox and
AI). Search and notifications also retain their topbar shortcuts. Settings stays in
the footer. Selecting a secondary section never removes its existing functionality.
The desktop sidebar can collapse. At 900px and below it becomes an explicit mobile
navigation dialog; page toolbars wrap, note lists stack and forms scroll within
viewport-bounded dialogs. Dense calendars/tables scroll inside their own regions
without making the document wider than the viewport. A day calendar is available
alongside the week grid. Keyboard focus is visible, form labels are explicit and
icon-only controls have accessible names. Native controls preserve platform input
and keyboard behavior. No new runtime dependency was added: Tailwind, shadcn,
Lucide, Motion and rich-editor packages are not required by this implementation.

## Implemented workspace interfaces

- Dashboard links to actual pages and resources; it does not fabricate activity.
- Notes expose a nested collapsible page tree, root/child creation, ancestor
  breadcrumbs and a centered block canvas. Summary batches are assembled into the
  complete tree; bodies load on selection. On phones the tree is a compact toggled
  list. A shared searchable slash/plus picker supports text, H1–H6, native bulleted/
  numbered lists, checkboxes and HTTP links. Native drag handles and up/down actions
  retain UUIDs; block removal is confirmed. Safe text/heading and list-style changes
  preserve data. Manual saves and Ctrl/Cmd+S retain page versions, duplicate-submit
  guards, partial-save recovery and explicit conflict reload. Page navigation offers
  save, stay or discard, with browser unload protection. Compact page menus expose
  parent moves, private links and branch trash/restore. Existing event backlinks and
  material references remain below the body. See [notes UI and future capability
  inventory](../development/notes.md#page-workspace-ui-2026-10-28). Rich formatting,
  nested blocks, revision history and collaboration remain outside the schema/UI.
- Materials provide bookmarks, metadata, trash/restore, processing retry, downloads,
  retained quotas and the existing reservation/raw-upload contract. An interrupted
  upload rechecks metadata before retrying the same reservation. No remote fetching
  or new file processing is performed in the browser.
- Collections/tags expose explicit page/event membership and safe removal of
  references. Page choices are bounded to 200; event choices use the loaded calendar
  week. Member lists paginate. Broader selection needs a future search picker.
- Databases expose definitions, seven typed property kinds, stable select-option
  IDs, schema/version checks, recoverable fields/records and existing/new page
  records. Saved table views support typed filters, sorting and visible columns;
  date-bound calendar views support day/week/month. Editing fetches the full record
  and PATCH sends touched fields only, preserving hidden/null values. Date-only
  values stay dates; timed inputs require explicit offsets. Timed end midnight is
  exclusive. Date edits use record forms; drag moves and mixed event/database
  display remain API-only. No formulas or task behavior is implied by record fields.
- Search uses the existing filtered full-text endpoint and renders snippets as text,
  never HTML. Results open the selected page or material.
- The inbox supports unread filtering/read marking. Event details create one-shot
  reminders; the pending list displays the latest 50 and permits cancellation.
  Task deadlines, recurring reminders and other delivery channels are unavailable.
- Settings edit display name/timezone and upload/delete a private avatar. Timezone
  changes refresh the session/calendar without rewriting event instants. Avatar
  files use the existing raw API and limits, never public optimized-image caching.

Actions show pending/success/error feedback and recoverable destructive operations
require confirmation. No private query data, drafts or credentials are persisted in
local/session storage. Request cancellation and the per-identity query boundary
also cover all newly mounted panels.

The current weekly calendar is rendered with React and CSS. Unused Zustand and
FullCalendar packages were removed during the 2026-10-21 audit; they remain target
stack candidates in the primary architecture, not current runtime dependencies.
The calendar uses backend-resolved events. Personal-event boundaries support native
pointer resizing and keyboard preview/commit over the existing versioned PATCH API.
Event movement and availability calculations remain unimplemented. Permissions,
schedule resolution and planning rules remain backend-owned. Clicking a calendar
entry opens a dedicated detail screen; editing a personal event is an explicit next
action. The screen exposes notes, note-owned materials, related events through an
explicit shared note, and reminders. Official occurrences remain read-only. Late
related-event reads cannot replace a newer navigation choice or a private draft.
See [calendar interaction contracts](../development/calendar.md#calendar-ui-2026-10-28).

## Target product responsibilities

Status: partially implemented. Future UI includes official-event override editing,
saved event-calendar views, mixed date projection and task scheduling after their
backend slices. [AI-04](../development/ai-04.md) implements chat, sources,
instructions, connections and usage; AI-07 adds confirmed proposals as described
below. Automatic actions remain deferred. Subjects
are optional navigation. Date labels and time reservations must be distinguishable.
The planned AI write UI will expose exact proposals/confirmation and
explicit automatic-action permission management. Shared editing and formulas are deferred.

Follow [workspace requirements](../product/workspace.md) and resolve editor/collaboration
scope in [open decisions](../product/open-questions.md) before choosing UI contracts.
The block editor preserves the existing document schema; database interfaces use
the existing saved-view API without introducing a second query language.

## Current verification and runtime

ESLint uses Next.js's accessibility, React and TypeScript rules. `tsc --noEmit`
provides type checking. Playwright runs Chromium tests against the built frontend:
shell/connectivity success/failure, verification/reset link handling and workspace flows.
Workspace tests cover account isolation/session expiry, registration/login and optional
group onboarding, CSRF-protected personal-event and task writes, read-only official events, queued/fast
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
Workspace content tests additionally cover note UUID/version/conflict recovery,
raw material uploads, hidden database fields, schema/option identities, typed saved
view queries, existing-page records, date-only/end-exclusive calendar entries,
reference removal without content deletion, search text safety, reminders, inbox,
profile/avatar writes and private draft cleanup. Responsive tests capture calendar,
note-editor and dialog screenshots at 1440, 834 and 390px, including dark mode.
Browser tests mock API responses; they are not live storage/email/IIS integration
checks. Backend tests cover PostgreSQL/Redis/SMTP separately. Verification history
in backend guides describes the original backend slices, not a rerun during UI work.

2026-10-22 frontend redesign verification: ESLint, TypeScript, production build,
all 124 Chromium Playwright tests, `docker compose config --quiet` and local
Markdown links passed. Screenshots were inspected at desktop/tablet/mobile sizes;
a visually hidden table heading escaping its mobile scroll container was corrected.
An additional local check matched 19 recorded browser mutations to actual FastAPI
routes and validated their 13 JSON bodies with the backend Pydantic DTOs, without
starting a backend lifespan or contacting external services. This checks transport
compatibility, not live integration. Backend Ruff/Pyright/pytest were not rerun
because backend code is unchanged.

Rendering errors use App Router `error.tsx` and `global-error.tsx` fallbacks with
a retry action and fixed JSON browser diagnostics. Failed health checks and email
verification/reset requests log safe event/status metadata; their responses can
include the backend request ID. Error messages, stacks, URLs and token fragments
are omitted from these diagnostics. Browser logs remain local to DevTools; no
remote telemetry SDK is installed. See [logging](../development/logging.md).

ESLint 9 is retained because the installed Next.js React plugins fail with ESLint
10. TODO: upgrade lint tooling when those plugins support ESLint 10.

The 2026-10-21 dependency audit found no production npm advisories. The development
toolchain reported five affected package entries from one unpatched
[braces advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm). It affects
repository glob processing in the ESLint chain. Recheck `npm audit` when updating
tooling; its proposed forced downgrade to eslint-config-next 14 is incompatible
with Next.js 16. Do not suppress the finding or apply that downgrade blindly.

The Dockerfile builds Next.js standalone output and serves it as the non-root
`node` user. No extra UI framework, font download or bundling orchestrator is used.
`npm run build` includes static assets in that standalone output; `npm start` runs
the same standalone server used by Docker.


AI-07 extends the local AI chat with exact before/after cards, one decision for a related
batch, stored terminal outcomes and navigation to current pages/events. Cards appear after
run completion and survive reload; confirmation does not call the model. Expired or stale
proposals cannot apply, and source fingerprints expose changed official facts even when
numeric versions match. See [confirmed action contracts](../development/ai-07.md).
Activation remains pending.

Executed on 2026-10-25 for the task screen: frontend lint, TypeScript typecheck,
production build, all **105 Playwright tests** (including four task flows), and
quiet base Compose validation passed. Playwright used a temporary Chromium shell;
no deployment or application database migration was performed. The tests mock
task HTTP responses and do not replace backend PostgreSQL integration coverage.

Executed on 2026-10-25 for task branch trash: frontend lint, TypeScript
typecheck, production build, **106 Playwright tests** (including the trash and
restore flow) and quiet base Compose validation passed. The browser test uses
mock task HTTP responses; backend tests separately exercise PostgreSQL. No
application database migration or deployment was performed.

Executed on 2026-10-25 for workspace/task integration: frontend lint, TypeScript
typecheck, production build and all **129 Chromium Playwright tests** passed.
The combined suite covers task editing, conflicts, hierarchy, branch recovery,
account isolation and the existing workspace panels. Task navigation and native
dialogs were exercised at 1440, 834 and 390px; light/dark screenshots were
visually inspected. Quiet base Compose validation also passed.

Backend code is unchanged by this integration. Ruff, Ruff format check, Pyright
and the default backend pytest suite passed: **1020 passed, 607 skipped,
1 warning**. Native PostgreSQL/Redis/S3 integration services were not configured
for this run; the warning is the existing Starlette/httpx deprecation. Earlier
dated native-service results remain separate evidence. No application database
migration, deployment or provider call was performed.

Executed on 2026-10-28 for the notes page workspace: frontend lint, TypeScript
checking, production build and all **151 Chromium Playwright tests** passed, along
with quiet Compose validation, changed-document local file links and diff checks.
The suite includes hierarchy across metadata batches, child creation, dirty-page
navigation, version conflicts/partial-save retries, native unload cancellation,
slash/plus keyboard controls, stable block IDs, list editing, drag ordering, link
editing/copying and deep-tree overflow. Light/dark screenshots were inspected at
1440, 834 and 390px. Browser tests mock HTTP responses; backend Ruff/Pyright/pytest
and live backend integration were not rerun because backend code/contracts are
unchanged. No application deployment, migration or real AI-provider call occurred.

Executed on 2026-10-28 for contextual calendar navigation and personal-event resizing:
frontend lint, TypeScript checking, production build, all **162 Chromium tests**,
quiet Compose validation, changed-document file links and diff checks passed. The
11 calendar regressions were also rerun after the final copy/screenshot adjustments.
Light/dark event-detail screenshots were inspected at 1440, 834 and 390px. Coverage
includes pointer/keyboard resize, cancellation, duplicate-write guards, stale versions,
service failures, midnight clipping, repeated DST hours, compact navigation, linked
notes/materials and abandoning late navigation reads after draft editing. Browser APIs
are mocked; no real provider traffic, deployment or running-database migration occurred.
Backend checks/live integration were not rerun because backend code and contracts
are unchanged.
