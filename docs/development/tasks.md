# Tasks: Incremental P-06 Delivery

Updated: 2026-10-25.
Status: task create/read/list/update, owner-scoped subtask hierarchy and recoverable
branch trash are implemented with a browser task screen. Dependencies, page links,
work blocks and availability are not implemented.

## First increment: independent task create/read/update

The first increment delivers standalone tasks without academic profiles, subjects,
pages or database records. It does not implement the whole P-06 roadmap.
`tasks` owns task state, deadline and effort. A deadline does not reserve time.
Checkboxes and database records do not create tasks or synchronize task status.

| Field | Contract |
| --- | --- |
| `id` | Server-generated UUID |
| `user_id` | Session-derived owner, never accepted or returned by HTTP DTOs |
| `title` | Trimmed, 1–200 characters |
| `description` | Nullable plain text, up to 10,000 characters; whitespace preserved |
| `status` | `todo` (default), `in_progress`, `done`, `cancelled` |
| `priority` | `low`, `normal` (default), `high`, `urgent` |
| `deadline_at` | Optional exact timestamp with an explicit UTC offset, normalized to UTC |
| `estimated_minutes` | Optional strict integer, 1–525600 |
| `parent_id` | Optional same-owner task UUID; null denotes a root (second increment) |
| `trashed_at`, `trash_batch_id` | Nullable paired branch-trash markers; server-managed |
| `version` | Positive optimistic version; starts at 1 and increments on accepted updates |
| `created_at`, `updated_at` | Server-generated timezone-aware timestamps |

Reject NUL/invalid Unicode in text, unknown fields, naive/epoch/date-only deadlines,
coercible effort/version values and explicit null for title/status/priority.
Past deadlines are valid. `is_overdue` is derived at read time: deadline is before
the server clock, task is not trashed and status is `todo` or `in_progress`; it is not stored.
All explicit status transitions, including reopening, are supported for standalone
tasks. No automatic scheduling, completion or calendar entry is created.

### Implemented HTTP contract

All paths are under `/api/v1/tasks`:

| Method | Suffix | Behavior |
| --- | --- | --- |
| POST | empty | Create; 201 task detail |
| GET | empty | Paginated summaries, without descriptions |
| GET | `/{id}` | Owned task detail |
| PATCH | `/{id}` | Partial update with `expected_version`; 200 task detail |
| POST | `/{id}/trash` | Move the active branch to trash with `expected_version`; 200 task detail |
| POST | `/{id}/restore` | Restore an owned trash-batch root with `expected_version`; 200 task detail |

Lists accept optional `status`, `priority`, `parent_id`, `roots_only` and `trashed`, limit 1–200 (default 100), offset
0–2147483647 (default 0), ordered by creation time then UUID. They return
`{items, limit, offset}` without a total-count promise. Details contain all fields
except the owner; summaries omit descriptions. Both include `parent_id` and `is_overdue`.
The default list includes untrashed roots and descendants. `trashed=true` selects
trashed tasks. `parent_id` selects direct children;
`roots_only=true` selects roots. Supplying both is invalid; a missing or foreign
parent ID returns the same 404. Owned trashed detail remains readable for recovery.

PATCH requires at least one editable field. Omitted fields are preserved; explicit
null clears only description, deadline, effort or parent. ID/owner/timestamps/version are
protected. `expected_version` is a strict integer in 1–2147483646. A stale version
returns 409 with `code=task_version_conflict`, without changing data.

Reuse completed-registration/session authentication, no-store responses and exact
Origin/CSRF guards on writes. Missing and foreign IDs share a 404. Invalid input is
422; database/commit failures use the existing sanitized 503 response. Success is
returned/logged only after transaction commit; logs never contain task text.

Writes recheck and lock the canonical active user. The repository additionally
constrains updates by ID, owner and expected version. Repositories/services never
commit independently. Lists and reads refresh canonical state rather than trusting
the SQLAlchemy identity map.

Alembic `0022_tasks` follows `0021_google_email_confirmations` and creates only task
storage and its owner/creation index. It refuses
to downgrade populated task storage. User deletion cascades to owned tasks.
Alembic `0023_task_hierarchy` adds an optional parent reference, owner/parent index,
same-owner composite foreign key and self-parent check. Existing tasks remain roots.
Downgrading refuses to discard non-null parent links. Alembic `0024_task_trash`
adds the paired nullable markers, owner-scoped indexes and a check that both
markers are set or both are null. It refuses to downgrade while any task is trashed.

Revision `0032_merge_ai_tasks` joins `0024_task_trash` and
`0031_ai_action_proposals` into one Alembic head. It changes no tables and preserves
both migration histories. Upgrading from either branch applies the other branch's
missing migrations; it does not require resetting existing data or revision IDs.

### Example

After normal completed-registration authentication and CSRF bootstrap:

```http
POST /api/v1/tasks
Content-Type: application/json
Origin: <configured frontend origin>
X-CSRF-Token: <current token>

{
  "title": "Prepare the laboratory report",
  "priority": "high",
  "deadline_at": "2026-10-30T18:00:00+03:00",
  "estimated_minutes": 90
}
```

Use the returned UUID with `GET /api/v1/tasks/{id}`. Change only supplied fields
with PATCH, for example `{"expected_version":1,"status":"in_progress"}`.
Re-read after a version conflict. No physical DELETE or permanent purge route is
provided. Parent IDs are supported by
the second increment below.

`is_overdue` uses the current server clock; it can change between reads without a
version change. Offset-aware deadlines are stored as instants, not calendar events.
There is no automatic POST retry/deduplication contract; submit task creation once.

### Verification

Domain/service tests cover validation, null/omitted semantics, all standalone status
transitions, exact overdue boundaries, eligibility and optimistic versions.
PostgreSQL tests cover owner-scoped persistence, independent sessions, rollback,
constraints, user cascade, preserving upgrade/downgrade and metadata parity. HTTP
tests cover real sessions, completed registration, CSRF, isolation, private logs,
concurrent edits and sanitized write failures. Reuse `AUTH_TEST_DATABASE_URL` and
`AUTH_TEST_REDIS_URL` against disposable services; unset variables skip those tests.

Executed on 2026-10-21: Ruff, Ruff format check, Pyright, quiet base Compose
validation and the full backend pytest suite against disposable PostgreSQL 18 with
pgvector and Redis 7.4: **1604 passed, 3 skipped**. The three skipped tests require
separate native S3 configuration (avatar storage, material storage and file jobs).
The existing Starlette/httpx deprecation warning remains. Migration checks used
only disposable schemas; no running application database migration or deployment
was performed. Frontend verification was outside this backend-only increment.

Executed on 2026-10-25 for the subtask increment: Ruff, Ruff format check,
Pyright, quiet base Compose validation and the full backend pytest suite against
disposable PostgreSQL 18 with pgvector and Redis 7.4: **1619 passed, 3 skipped,
1 warning**. The skipped tests require separate native S3 configuration; the
warning is the existing Starlette/httpx deprecation. Hierarchy-specific checks
cover owner and database constraints, preserving migration round-trips, deep
chains, cycles, descendant completion, combined parent/status updates, HTTP
authorization and concurrent writes. No application database migration or
deployment was performed; frontend checks were outside this backend-only slice.
After adding the owner-deletion cascade assertion, its targeted PostgreSQL test
was rerun and passed; the full-suite count above precedes that test-only edit.

## Second increment: subtask hierarchy

Status: implemented, backend only, on 2026-10-25. The owner confirmed these rules;
the task schema and API now accept `parent_id`. Existing task IDs, owner scope and
standalone operations are preserved.

- A task may have one parent or no parent. Nesting has no product-imposed depth limit;
  every parent chain must be finite and acyclic.
- Parent and child must belong to the same user. A task cannot parent itself or be
  moved beneath any of its descendants.
- Creating a child or moving a task changes only the requested task's parent
  relationship; it does not propagate title, deadline, status or other business
  fields to related tasks. Normal version and update-timestamp changes on the
  moved task still apply.
- A parent can transition to `done` only when every descendant is
  `done` or `cancelled`. This check does not complete descendants automatically.
- An active (`todo` or `in_progress`) task cannot be created, moved or reopened
  anywhere beneath a `done` ancestor. This keeps the completion rule true after
  later writes, including writes to deeper descendants.
- A PATCH that changes both `parent_id` and `status` validates the resulting
  hierarchy and statuses together, atomically, before applying either change.

Use `POST /api/v1/tasks` with an optional `parent_id` to create a child. Use
`PATCH /api/v1/tasks/{id}` with `expected_version` and `parent_id` to move it;
explicit null makes it a root. `GET /api/v1/tasks?parent_id={id}` lists direct
children; `GET /api/v1/tasks?roots_only=true` lists roots. All existing list
filters and pagination still apply. A hierarchy violation returns 409 with
`code=task_hierarchy_conflict`; stale versions keep `task_version_conflict`.
Missing or foreign parent IDs return `task_not_found` without revealing ownership.
No fixed nesting-depth limit is imposed. Services validate ancestor chains under
the existing owner write lock, and the repository checks all descendants through
a recursive query within the caller's transaction.

Cancelling a parent currently changes only that task's status and does not change
descendants. A future branch-cancellation policy needs an explicit decision.
These hierarchy rules do not add dependency edges or scheduling. Trashed descendants
are excluded from completion checks; restoration revalidates completed ancestors.

## Third increment: recoverable branch trash

Status: implemented on 2026-10-25. `POST /{id}/trash` marks the selected task and
its currently untrashed descendants with the selected task's ID as their
`trash_batch_id`. Already trashed descendants retain their earlier batch markers.
Each changed task receives a new version and `updated_at`; task content, parent,
status and deadline are preserved. No task is physically deleted.

Only the selected root of a trash batch can be restored with `POST /{id}/restore`.
The operation restores only tasks bearing that batch ID. Descendants deleted
earlier remain trashed and can be restored separately through their own batch
roots after their parents are active again. Restoration rejects a trashed parent
chain and rejects an open batch (`todo`/`in_progress`) beneath a `done` ancestor.
Active task creation/moves cannot target a trashed parent, and trashed tasks
cannot be edited or trashed again. Owner checks, CSRF and optimistic versions
apply to both writes. A stale version returns `task_version_conflict`; invalid
trash state returns `task_trash_conflict`; completed-ancestor violations return
`task_hierarchy_conflict`. Missing and foreign tasks share `task_not_found`.

There is no retention deadline, purge worker or permanent-delete API in this
increment. Trash is recoverable until a later explicit policy is implemented.

Executed on 2026-10-25 for branch trash: Ruff, Ruff format check, Pyright and
the full backend pytest suite against disposable PostgreSQL 18 with pgvector
and Redis 7: **1624 passed, 3 skipped, 1 warning**. The skipped cases require
separate native S3 configuration; the warning is the existing Starlette/httpx
deprecation. Migration preservation, branch batches, owner/CSRF/version guards
and completed-ancestor behavior were exercised. Frontend lint, typecheck,
production build and **106 Playwright tests** also passed; quiet base Compose
configuration was validated. No application database migration or deployment
was performed.

## Remaining manual P-06 increments

Status: not implemented. These decisions are not delivered by the current task APIs:

- Cycle-safe dependencies and optional page links. Dependencies warn rather than block.
- Calendar occupied/free/conflict queries over the complete busy set; query-supplied
  availability windows, not saved working hours.
- Versioned future-only manual task blocks. Completion/cancellation/trash cancels
  future blocks; elapsed sessions never complete tasks automatically.
- Explicit acknowledgement and locked revalidation for overlaps and uncertain IIS
  data. Source period boundaries alone must not be claimed as complete coverage.
- Additive opt-in task-block/deadline calendar display, preserving existing APIs.

Automatic planning, saved work preferences, task/deadline reminders and all AI
runtime remain outside these backend increments and unimplemented.

## Browser task screen

Status: implemented on 2026-10-25 in the existing `/workspace` shell. The sidebar
and mobile navigation open a paginated task list with status/priority filters.
The integrated workspace uses the shared navigation, API client, native dialogs
and light/dark theme tokens alongside pages, databases, materials and other panels.
Selecting a task shows its description, status, priority, deadline, effort, parent
and direct children. The create/edit form covers all current task fields; the
selected task can create a child, move beneath a chosen task or become a root.
The parent picker paginates through existing tasks; the backend remains authoritative
for cycles, ownership and completed-branch rules. There is no UI depth limit.

The screen uses the existing completed-registration browser session, fresh CSRF on
writes, no-store reads and per-identity query cache. It handles version and hierarchy
conflicts explicitly; a stale editor draft is retained until the user chooses to
reload. Deadline input and display use the profile timezone, including ambiguous
and nonexistent local-time handling. Deadlines do not reserve calendar time.
The screen has active/trash list tabs, a confirmed branch-trash action and a
restore action only for batch roots. Trashed task details are read-only; members
explain why they cannot be restored individually. There is no
task/calendar block, dependency, page link or reminder UI in this slice.

The 2026-10-25 workspace integration preserves these task flows in the redesigned
shell. Combined browser and responsive verification is recorded in the
[frontend guide](../architecture/frontend.md#current-verification-and-runtime).
