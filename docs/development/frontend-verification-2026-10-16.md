# Frontend review fixes and verification

Date: 2026-10-16.
Status: all six reported frontend findings fixed, plus home navigation, retained split
failure wording and first-import source initialization.

## Branch and integration

Local branch: `olya/ui`. Individual fix commits and their original authors are preserved.
Frontend baseline: `origin/olya/ui` at `d5115cb`. Backend baseline: `main` at `457919d`.
Commit `a80bf9b` integrates main into the UI branch and resolves the four existing
documentation conflicts while preserving P-07/P-08 and the implemented frontend.
Main and the remote branches were not changed. No push, deployment or merge into
main was performed. Runtime, configuration and test files are byte-for-byte identical
to the code verified below. Transferring the history changed commit hashes; it did
not change the implementation. These are the original dated verification results,
not checks rerun solely for the history transfer.

## Cohesive fix commits

| Commit | Review finding / behavior |
| --- | --- |
| `0708eca` | A session owns its query client and mounted forms. Account changes, logout and expiry discard private state and cancel reads. |
| `6e01eb1` | Sync presentation derives from queries/request state; effect-driven duplicate flags and the lint violations are removed. Timers clean up with their request. |
| `784b81d` | Sync completion must advance the selected source beyond its pre-request snapshot. Old ready data is not new success; delayed workers remain polled. |
| `ccf810b` | Full-day grid, clipped overlapping day segments, continuation agenda, uncapped duration and original-interval editing. |
| `ca27763` | API/profile timezone drives civil dates, navigation, display and editing; DST gaps and repeated times are explicit. |
| `b95d973` | Workspace auth/group/CRUD and failure-recovery browser coverage, including returning users with an existing profile. |
| `5e0ccae` | The home page exposes the workspace through a calendar link. |
| `6a1608b` | A retained historical split rejection asks for another import without claiming the current backend lacks verified split support. |
| `1b884c6` | A documented group-events 404 initializes an empty baseline for the first import; service outages remain errors. |

## Executed checks

- Frontend ESLint: passed.
- Frontend TypeScript: passed.
- Production build: passed, including standalone static-asset copy.
- Full deterministic Playwright suite: **37 passed** (the previous suite had 11).
- Base Compose config: passed with public example settings.
- Home Compose exposure, secret isolation and proxy trust checker: passed with dummy
  validation values; no service deployment was performed.
- Backend Ruff and Ruff format: passed (353 Python files).
- Backend Pyright: passed, zero errors/warnings.
- Full backend pytest: **1456 passed**, no skipped tests. The run emitted 618
  dependency deprecation warnings (Starlette/httpx and Alembic path configuration).
- `git diff --check`: passed before each fix commit.

Browser regressions cover two-account privacy and session expiry, login/registration,
optional group selection and subgroup changes, personal CRUD with version checks and
CSRF/cookie/Origin assertions, read-only official details, source failures/retries,
old-ready/queued imports, fast completion and delayed worker recovery, overnight and
week-boundary intervals, long events, midnight exclusivity, differing browser/profile
timezones, week navigation, DST gaps/folds and non-hour offsets. No dependency was added.

The disposable backend runner initially mixed smoke settings into test fixtures and
used an incorrect test URL during setup. Those attempts were stopped; final backend
results must come from a clean test environment and its dedicated empty database,
separate from the migrated live-browser database.

## Native browser / live IIS verification

The final built frontend reached the real API, PostgreSQL, Redis, Celery worker and
public IIS adapter using a new disposable account. No API responses were mocked.

- Group **553501**, subgroup **1**: import accepted (202), source reached `ready`,
  and **17 official events** were visible for October 12–18.
- Browser timezone `UTC`, profile/calendar timezone `Europe/Minsk`.
- A Monday **00:30 Minsk** personal event rendered at its actual early-hour position
  and was stored as **2026-10-11T21:30:00Z**.
- Personal event create/edit/delete returned **201/200/204**; official events survived.
- Desktop 1440×1000 and mobile 390×844 were inspected. The mobile document width stayed
  390 px; the week uses horizontal scrolling inside the calendar.
- The native check exercised a genuinely never-imported group source (404) before
  profile selection, then completed its first import successfully.

Screenshots and sanitized live response metadata are retained with this chat's
verification artifacts. Test databases, broker and object storage were disposable and were removed after
verification; native API/worker/browser processes were stopped. No production data,
email delivery or deployment was used.

## Limits

Chromium was checked. Firefox/Safari, a complete assistive-technology audit, public
hosting, Docker image builds, OAuth/SMTP delivery and production/concurrent-user
capacity were not checked. Live IIS verification covers one group/date range and
is not a guarantee of upstream coverage or availability for every group.
Pages, tasks, materials/search, reminders/inbox and saved-view/database UI remain
outside this frontend slice. Day/month views, drag/resize and recurring/all-day
personal events remain unimplemented.
