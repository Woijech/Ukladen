# Task work planning

Status: implemented locally, including browser controls and AI integration under
[AI-10](ai-10.md). Application activation and real-model quality remain unverified.

Tasks expose nullable `remaining_minutes` independently of the original estimate.
Existing records and newly estimated tasks retain an unknown remainder until the
owner supplies it. Zero means explicitly no work remains; it does not change task
status. Session passage, movement, cancellation and task completion never infer or
rewrite this value.

`/api/v1/tasks/planning` uses completed-registration sessions, no-store responses
and CSRF for writes. Requests reject additional fields.

- `GET/PUT /preferences`: weekly windows (Monday=0, start/end minute 0..1440),
  session length 15..240 (default 45), breaks 0..120 (default 15). PUT requires
  `expected_version`; absent preferences have version 0. Overlapping windows fail.
- `GET /sessions?starts_at=...&ends_at=...`: owner-only bounded interval, including
  cancelled history. Sessions have task ID, interval, pinned/cancelled state/version.
- `POST /sessions/check`: task, interval and optional existing session ID returns
  availability/conflicts and a fingerprint, excluding the edited session.
- `POST /sessions`: same values plus the reviewed `snapshot`, optional `pinned`,
  `acknowledge_conflicts`, and existing session ID/expected version for movement.
  Intervals must start in the future, last at most 24 hours and target an active
  task. Conflicts or unverified expected IIS coverage require explicit manual
  acknowledgement. A changed snapshot rejects the request even with acknowledgement.
- `PATCH /sessions/{id}`: expected version plus pin state or cancellation. Past,
  started and cancelled sessions are protected. A manually pinned session may be
  moved explicitly by its owner; pinning protects it from general replanning.

Writes share the canonical owner lock with task/calendar/profile changes. Manual
session placement also holds a read lock on configured schedule source rows,
serializing with schedule imports. No external call runs under these locks.
Task closure and branch trash cancel future sessions in the same transaction;
restoration does not recreate cancelled reservations. Foreign IDs match absent IDs.

Availability includes active task sessions independently of display filters;
legacy calendar event response enums remain unchanged. Dates/deadlines stay
nonblocking. Weekly boundaries use the profile timezone and reject ambiguous or
nonexistent DST local times, requiring explicit dated windows instead.

Migration 0035 preserves existing task values. Populated planning data prevents
lossy downgrade. No real provider request or application migration was performed.

## Deterministic plans

Implemented locally on 2026-10-28. `POST /plans` accepts task IDs, an explicit
future interval of at most 31 days, optional dated windows and `replan`. Dated
windows override this request only. Without them, weekly windows expand in the
profile timezone. Missing windows yield a conditional preview. Inputs are bounded
at 100 selected tasks, 2,000 current tasks, 10,000 dependencies/reservations and
512 proposed sessions; excess facts reject rather than disappear silently.

The planner expands selected parents to leaves and counts each leaf once. It
requires explicit remaining minutes, orders eligible work by deadline/priority,
respects predecessor completion before successors, and reserves 45/15 sessions/
breaks by default. A final remainder may be shorter than 15 minutes. It preserves
suitable existing unpinned reservations before adding new sessions. Replanning
may cancel future unpinned sessions (including manual ones) entirely inside its
interval; pinned, started, past and out-of-range sessions remain protected.
Protected future reservations consume the explicit remaining budget. Past work
never does. Unresolved predecessors, unknown remainder and unplaced minutes are
reported separately. The greedy algorithm does not claim a global optimum.

`GET /plans/{id}` returns the immutable preview. `POST /plans/{id}/apply` requires
its exact `digest`, plus `accept_partial=true` for an incomplete plan. Previews
expire after 24 hours or when their interval starts. The whole plan revalidates
all captured inputs under owner/source locks; any change rejects all writes.
New sessions, cancellations and the durable applied receipt share one transaction.
Replay of an applied plan returns its receipt even if tasks later change. Plan
receipts belong to the owner and survive chat retention; account deletion removes
them. Migration 0036 refuses a lossy populated downgrade.

Expected but unknown/stale official coverage permits conditional previews only.
The verified IIS contract currently provides no completeness proof; a ready
status or term dates cannot lift that restriction. Users without academic profiles
can apply plans against their personal calendar and task sessions.

## Browser and calendar display

The Tasks screen exposes dependencies and page links, explicit remaining minutes,
weekly preferences, planning and manual session controls. Plan previews show current
protected sessions and the exact old reservations to cancel. Changes require a new
preview; partial work has a separate acceptance checkbox. Session placement has its
own check/confirmation and optional explicit manual acknowledgement of conflicts.

`GET /api/v1/tasks/planning/calendar` is an additive owner-scoped projection with
`starts_at`, `ends_at`, `include_sessions` (default true) and `include_deadlines`
(default false). It returns titled active sessions and optional nonblocking open-task
deadlines. Calendar display filters change no underlying busy calculations. Legacy
`/calendar/events` response types remain unchanged. The browser shows this task
projection separately from official/personal occurrences and opens session controls
from it. Full dates, timezone and pin state remain visible.

## AI-10 bridge

The existing LangChain/LangGraph runner registers `read_tasks`,
`get_calendar_availability` and `preview_task_plan`. The last saves a derived preview,
never business writes; its per-run cache revalidates the stored preview before reuse.
Task reads include current status, explicit remainder, versions, bounded dependency
facts and historical provenance. Explicit source scopes can select task IDs; full
page/material processing cannot silently broaden to task/calendar sources.

`propose_actions` supports `task_create`, `task_update` and `task_plan_apply` alongside
the existing AI-07 operations. Creation carries a typed draft, real read references
and locations, estimate origin, uncertainties and advisory duplicates. Earlier
create actions can be referenced by parent/predecessor indices. Task updates use
ordinary service validation and expected versions. One complete task plan is its
own batch. Confirmation uses normal task/planning/relations services in the same
transaction as the AI-07 receipt. No model executes during confirmation.

`POST /api/v1/ai/proposals/{id}/revise` creates a new immutable preview, superseding
the old pending one. It does not apply edits. The browser edits extracted task title,
body, priority, deadline, estimate and remainder before a new explicit confirmation.
Existing source evidence must still validate; changed sources require fresh reads.
Batches retain the existing 8-action / 16 KiB argument bound. Larger or partially read
sources require bounded further processing/proposals with explicit coverage limits.

Migrations 0037/0038 retain task provenance and allow independently reviewed proposal
revisions. Populated downgrades are refused. Provenance survives chat cleanup;
relations and task creation are atomic. Possible duplicates never merge automatically.
Source record validation includes the page/schema locator even when its record
version is unchanged. No checkbox or database-record synchronization is introduced.
