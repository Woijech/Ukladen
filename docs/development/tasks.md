# Tasks: Incremental P-06 Delivery

Updated: 2026-10-25.
Status: independent task create/read/list/update implemented, backend only.
Hierarchy, trash, dependencies, page links, work blocks and availability are not implemented.

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
| `version` | Positive optimistic version; starts at 1 and increments on accepted updates |
| `created_at`, `updated_at` | Server-generated timezone-aware timestamps |

Reject NUL/invalid Unicode in text, unknown fields, naive/epoch/date-only deadlines,
coercible effort/version values and explicit null for title/status/priority.
Past deadlines are valid. `is_overdue` is derived at read time: deadline is before
the server clock and status is `todo` or `in_progress`; it is not stored.
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

Lists accept optional `status` and `priority`, limit 1–200 (default 100), offset
0–2147483647 (default 0), ordered by creation time then UUID. They return
`{items, limit, offset}` without a total-count promise. Details contain all fields
except the owner; summaries omit descriptions. Both include `is_overdue`.

PATCH requires at least one editable field. Omitted fields are preserved; explicit
null clears only description, deadline or effort. ID/owner/timestamps/version are
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
Re-read after a version conflict. Parent/source IDs and deletion/lifecycle routes
are not supported in this increment; no stub APIs advertise future functionality.

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

## Agreed later manual P-06 increments

Status: not implemented. These decisions are not delivered by basic task APIs:

- Owner-scoped subtasks, cycle-safe dependencies and page links. Dependencies warn;
  a completed parent requires all active descendants to be done/cancelled.
- Recoverable branch trash/restore; no physical task DELETE API.
- Calendar occupied/free/conflict queries over the complete busy set; query-supplied
  availability windows, not saved working hours.
- Versioned future-only manual task blocks. Completion/cancellation/trash cancels
  future blocks; elapsed sessions never complete tasks automatically.
- Explicit acknowledgement and locked revalidation for overlaps and uncertain IIS
  data. Source period boundaries alone must not be claimed as complete coverage.
- Additive opt-in task-block/deadline calendar display, preserving existing APIs.

Automatic planning, saved work preferences, task/deadline reminders, frontend and
all AI runtime remain outside the requested first increment and unimplemented.

### Confirmed subtask hierarchy contract (2026-10-25)

Status: not implemented. The owner confirmed these rules for the future hierarchy
slice; the existing task schema and API do not yet accept `parent_id`.

- A task may have one parent or no parent. Nesting has no product-imposed depth limit;
  every parent chain must be finite and acyclic.
- Parent and child must belong to the same user. A task cannot parent itself or be
  moved beneath any of its descendants.
- Creating a child or moving a task changes only the requested task's parent
  relationship; it does not propagate title, deadline, status or other business
  fields to related tasks. Normal version and update-timestamp changes on the
  moved task still apply.
- A parent can transition to `done` only when every non-trashed descendant is
  `done` or `cancelled`. This check does not complete descendants automatically.
- An active (`todo` or `in_progress`) task cannot be created, moved or reopened
  anywhere beneath a `done` ancestor. This keeps the completion rule true after
  later writes, including writes to deeper descendants.
- A PATCH that changes both `parent_id` and `status` validates the resulting
  hierarchy and statuses together, atomically, before applying either change.

The behavior of cancelling a parent with active descendants is not specified by
these confirmations; it needs a separate decision before that lifecycle rule is
implemented. These hierarchy rules do not add task trash, dependency edges or
automatic scheduling.
