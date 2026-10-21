# Tasks: Incremental P-06 Delivery

Status: implementation contract. Runtime is not implemented yet.

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

### Planned HTTP contract

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

The preserving Alembic migration creates only task storage and indexes. It refuses
to downgrade populated task storage. User deletion cascades to owned tasks.

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
