# Calendar reminders and in-app notifications

Updated: 2026-10-22.
Status: P-07 backend implemented, with event reminder creation, pending cancellation
and inbox UI; see the [frontend guide](../architecture/frontend.md). Tasks/deadlines
depend on P-06 and are not implemented. Recurrence, email, Telegram and push remain unavailable.

## Ownership and trigger contract

`reminders` owns one-shot reminder state; `notifications` owns the durable inbox.
Both use application services, caller-owned transactions and PostgreSQL persistence.
Calendar targets are resolved through `CalendarService`, including personal overrides
and academic group/subgroup authorization. No worker performs live IIS requests.

Create accepts `source: personal | official`, `event_id` and `minutes_before` (default
15, strict integer 0–43200). A personal target needs no academic profile. An official
target must be active and accessible in the current group/subgroup; skipped events
are rejected. Hidden events remain eligible. Database date projections and task IDs
are not supported targets.

`due_at = starts_at - minutes_before` uses elapsed minutes on the UTC timeline.
Calendar event APIs already require offset-aware timestamps; no naive local time,
implicit timezone or ambiguous DST conversion is accepted here. Profile timezone
changes do not move an existing trigger. Creation and editing require `due_at` to be
strictly in the future. A zero offset delivers at the event start.

Reminders retain their selected start time. Before delivery the worker resolves the
current target again. Moved, skipped, withdrawn, inaccessible or missing events
cannot produce obsolete notifications. A changed start cancels the reminder rather
than silently moving the trigger. Editing a pending reminder explicitly rebinds it
to the target's current start. A title-only edit uses the current title at delivery;
an end-time edit affects the expiry check. Notification titles are snapshots bounded
to 500 characters; source content is preserved.

## HTTP API

All endpoints require an active browser session and return `Cache-Control: no-store`.
Writes require the existing allowed Origin and CSRF cookie/header pair. Owner UUIDs
come from the session. Missing and foreign resources share a 404 response.

| Method | Route | Input/result |
| --- | --- | --- |
| POST | `/api/v1/reminders` | Create a pending reminder; 201 |
| GET | `/api/v1/reminders` | Paginated reminders, including terminal states |
| GET | `/api/v1/reminders/{id}` | Reminder details |
| PATCH | `/api/v1/reminders/{id}` | Required `minutes_before` and `expected_version` |
| POST | `/api/v1/reminders/{id}/cancel` | Required `expected_version`; cancel pending reminder |
| DELETE | `/api/v1/reminders/{id}?expected_version=N` | Delete reminder; 204 |
| GET | `/api/v1/notifications` | Paginated inbox; optional `unread_only=true` |
| GET | `/api/v1/notifications/{id}` | Historical notification details |
| POST | `/api/v1/notifications/{id}/read` | Idempotent first-read timestamp |

Lists accept `limit=1..200` (default 100) and `offset=0..2147483647` (default 0),
ordered by creation descending and UUID ascending. Responses contain `items`,
`limit` and `offset`. Reminder DTOs contain ID, source/event ID, minutes/start/due,
status, version and timestamps. Notification DTOs contain ID, reminder ID,
source/event ID, title/start snapshot, creation and nullable first-read time.
Neither exposes `user_id`.

Create/PATCH reject unknown fields, invalid offsets and null values with 422.
The target is immutable. PATCH requires a pending reminder; delivered/cancelled
reminders cannot be rearmed. Create a new reminder for a new delivery. Stale
versions, skipped targets and incompatible states return 409. Cancellation with
the current version is idempotent; a delivered notification cannot be recalled.
Read marking preserves its original timestamp and tolerates backward clock skew.

Example creation, using the normal authenticated browser CSRF headers:

```json
{"source": "personal", "event_id": "<event UUID>", "minutes_before": 15}
```

POST creates a distinct reminder on every successful request; multiple reminders
for one event are allowed. Delivery deduplication is per reminder UUID, not title
or event. There is no client-supplied idempotency key.

## Delivery, cancellation and recovery

Beat publishes `reminders.dispatch_due` every 30 seconds, independently of
`SCHEDULE_SYNC_ENABLED`. The task scans at most 200 pending due reminders ordered
by due time and ID. Each delivery has its own transaction. It takes the canonical
active-owner lock before reading current reminder state, matching calendar/reminder
mutation lock order. Concurrent sweeps and API writes therefore serialize; workers
recheck status and trigger after acquiring the lock. Schedule facts are evaluated
from committed local data, with the existing upstream identity/freshness limitations.

The notification insert and `pending -> delivered` transition commit together.
A unique notification `reminder_id` rejects replay inserts. Failures roll both
back; unrelated reminders in the selected batch continue. Celery retries sanitized
failures up to three times with exponential backoff. Late acknowledgement and
worker-loss redelivery are enabled. The next Beat scan remains the recovery path
after exhausted retries or lost broker messages; Redis is never authoritative.

Pending reminder edits replace the trigger in PostgreSQL; queued sweeps carry no
reminder payload. Cancellation changes status, and deletion removes the row, so
stale jobs cannot deliver either. Personal-event deletion cascades its reminders
through the owner-constrained foreign key, including legacy calendar deletion.
Official targets use a typed foreign key; source withdrawal/profile changes cancel
at the next due evaluation. Disabled owners are cancelled without notification.

After downtime, due reminders catch up only while their unchanged event has not
ended (`now < ends_at`); reminders for ended events are cancelled. A cancellation
committed before worker evaluation prevents delivery. A notification already
committed remains a historical inbox record, even after reminder/target deletion.
Its reminder/event UUIDs are snapshot references, deliberately without cascading
foreign keys; they do not grant access to a deleted or newly inaccessible event.
Deleting a user cascades both reminder state and their inbox.

If Redis/Beat/worker becomes unavailable:

1. Keep PostgreSQL intact; no per-reminder messages need reconstruction.
2. Restore Redis, one Beat instance and workers using the current backend image.
3. The next scheduled scan drains due batches, applying the expiry/target checks.
4. For an immediate scan, run
   `celery -A app.workers.celery_app:celery_app call reminders.dispatch_due`.

Delivery is periodic rather than exact to the second. A backlog drains in bounded
batches; no throughput or storage quota guarantee is provided. Permanent database
failures require operator repair. Records are retained until reminder/user deletion;
notification retention/purge and operational quotas are later work.

## Persistence and deployment

`0018_reminders_notifications` adds the two tables without changing existing
calendar data or HTTP contracts. Constraints enforce typed targets, personal-event
ownership, offsets, versions, statuses, trigger arithmetic and the delivery key.
Downgrade refuses to discard retained reminders or notifications. Empty-table
upgrade/downgrade and Alembic metadata parity are checked on disposable schemas.

Deploy with the normal migrate-before-process-start workflow and rebuild/recreate
API, worker and Beat. No new dependency, service, secret or environment variable is
needed. Worker task/failure logs omit titles, payloads and exception messages.

## Verification (2026-10-15)

Targeted PostgreSQL/Redis checks cover UTC/DST offsets, trigger boundaries,
ownership/subgroups, CSRF, optimistic updates, rollback, read idempotency,
concurrent delivery, committed target edits, historical inbox preservation,
broker catch-up, real Redis message decoding, registered task execution and retries.

Executed checks: Ruff, Ruff format, Pyright, complete backend pytest with disposable
native PostgreSQL 18/Redis services (1386 passed, 1 skipped), `docker compose config
--quiet`, local documentation links and Git whitespace checks. The skip was the
existing native SeaweedFS avatar check without test S3 configuration. The additional
backward-clock read assertion passed in its targeted persistence rerun. Frontend
checks and deployment were outside this backend slice.
