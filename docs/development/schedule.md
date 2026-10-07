# Official schedule storage

Status: implemented — verified dated expansion, PostgreSQL storage, background
synchronization and authenticated persisted-event HTTP endpoints.

The schedule module owns official university facts. Personal events, skipped lessons,
overrides, occupied time and free slots belong to calendar and are not implemented.
Existing public IIS read endpoints retain their response contracts.

## Persistence and identity

Alembic `0006_schedule_storage` adds `schedule_sources` and `official_schedule_events`.
One source belongs to one selected university group; events are shared across users.
Validated snapshots are JSONB metadata, never authoritative user preferences.
Event times are timezone-aware UTC; source dates and ranges use Europe/Minsk.

The store performs short transactions. A two-minute PostgreSQL lease with a UUID
claim token fences expired/replaced workers. No network operation holds a database
transaction. A successful import reconciles events atomically; errors retain the
previous snapshot and active events. Confirmed absence of a published schedule retires
events and records `unpublished`. Historical events are retained with `active=false`
for future calendar references; they are never silently deleted.

Exact content matches retain existing UUIDs, including reappearing rows. A unique
same-day subject/type/subgroup/note match retains its UUID across time, room and
teacher changes. Parallel ambiguous rows get new UUIDs. Changed dates or subject
labels are new occurrences: TODO stable upstream IDs or explicit reconciliation
are needed before transferring personal overrides across those changes. Notes are
part of identity because they can distinguish language classes.

Routine checks import sanitized fixtures; no test requires the live university API.
PostgreSQL tests reuse `AUTH_TEST_DATABASE_URL` with isolated schemas. Migration
upgrade/downgrade and Alembic metadata comparison are covered.

## HTTP API

Existing IIS GET endpoints keep their live-read contracts. New endpoints read
PostgreSQL without calling IIS, all require an active session and return no-store:

| Method/path | Behavior |
| --- | --- |
| `GET /api/v1/schedule/me/events?date_from=2026-10-05&date_to=2026-10-11` | Saved group and subgroup, including whole-group events |
| `GET /api/v1/schedule/groups/{group_number}/events?date_from=...&date_to=...&subgroup=1` | Imported group; omitted subgroup includes all |
| `GET /api/v1/schedule/events/{event_id}` | An event in the user's saved group/subgroup, including withdrawn historical records |
| `GET /api/v1/schedule/me/sync-status` | Import state and timestamps for the saved group |
| `POST /api/v1/schedule/me/sync` | Queue an update for the saved group, returns 202 after broker acceptance |

Both date parameters are required ISO dates. Bounds are inclusive Minsk calendar
dates and allow at most 366 days. The response is `{events: [...], source: {...}}`.
Each event includes UUID, group ID, kind, subgroup, timezone-aware start/end,
subject labels, actual lesson type, note, rooms, teacher IDs/names and active state.
`exam` identifies the source exam/session collection; its lesson type may be a
lecture, practical class or consultation. `announcement` never implies cancellation
or occupied time; calendar must resolve that separately. No stable subject or room
ID is manufactured from labels.

Source states are `not_synced`, `syncing`, `ready`, `unpublished`, `error` and
`unsupported`, with `last_attempt_at`, `last_success_at` and safe `error_code`.
Events and their source metadata come from one SQL statement for a consistent
snapshot. An initial unsynchronized profile returns an empty array with
`not_synced`; this is distinct from confirmed `unpublished`. A failed refresh
returns the previous active events with degraded source state. A `ready` snapshot
may also be old: clients should use `last_success_at` to display freshness.

No academic selection returns 409. Missing event, another subgroup's detail, or
an unimported group-number query returns a generic 404. Invalid dates/selectors
return 422. Storage/broker failures return sanitized 503 errors. The POST requires
existing Origin/CSRF protection and is limited to one request per group per minute
across sessions. Queue acceptance is not a completed import; poll sync-status.

## Synchronization and onboarding

After saving a group/subgroup through `PATCH /api/v1/academics/me`, clients may
POST the sync endpoint for an immediate queued import. Celery Beat also runs
`schedule.refresh_selected` every 60 seconds: it discovers distinct saved groups
through an academics-owned directory port and queues only due groups. Thus new
selections are discovered automatically even if the client closes after selection.
`SCHEDULE_SYNC_ENABLED` defaults to true and disables both periodic dispatch and
manual publication when false. `SCHEDULE_SYNC_INTERVAL_SECONDS` defaults to 3600
and accepts 60–86400. Settings are shared by API, worker and Beat.

The `schedule.sync_group` task validates its payload, creates bounded cookie-free
IIS clients, checks the upstream group identity, expands all supported rows and
atomically applies a complete snapshot. Payloads and errors contain no user
credentials. Publication and upstream calls run outside database transactions.
Each group has one canonical import; subgroup changes do not reimport it.
Expired worker leases can be reclaimed, and stale workers cannot overwrite a
replacement import. Periodic discovery recovers missed/expired queue publications;
there is no separate schedule outbox. Broker jobs expire after 120 seconds to
avoid accumulating obsolete work. Existing worker/Beat processes need the new
backend code and Alembic migration before enabling these tasks.

## Verified support and explicit limits

Regular recurrence follows the observed official Monday-based four-week academic
calendar. Exact-dated lessons, examinations/session rows and announcements retain
their dates. Next-period recurring rows require their own date bounds. Materialized
periods are bounded to 366 days per recurring row, with at most 20,000 distinct
events per import. Recurring rows require valid week numbers and increasing times.
Cross-midnight source rows are unsupported rather than assigned a guessed end date.

Authoritative split/exception/cancellation precedence is still unavailable. A split
row, undated announcement, undated exam or incomplete next-period bounds fails the
whole import as `unsupported` while retaining the last valid data. TODO obtain the
missing IIS contract before enabling those cases. Text notes are preserved, never
parsed as commands. Holiday colors do not suppress lessons. See the verified
[upstream contract](../integrations/bsuir-iis-public-api.md).

Teacher schedules and standalone announcements retain their existing live GET
endpoints. They are not independently imported into the group event store, avoiding
duplicate official lessons. Calendar resolution, personal overrides, free slots,
notifications and frontend UI remain separate, unimplemented modules.

## Verification (2026-10-07)

Ruff, Ruff format, Pyright and `docker compose config --quiet` passed. The full
backend suite ran with disposable PostgreSQL 18 and Redis 7.4: 1000 passed, one
existing S3 avatar integration check skipped because dedicated test storage
settings were not supplied. Checks include Alembic round trips, metadata parity,
concurrent/fenced claims, stable identity, offline subgroup reads, CSRF/rate limits,
periodic discovery and a real Redis queue round trip to the worker task.

A cookie-free live smoke expanded group 353501 into 313 official events covering
2026-09-01 through 2026-12-28. Group 310101 contains split rows and correctly
returned the unsupported outcome; its raw GET remains available. Live IIS calls
are a separate manual smoke and are not part of ordinary pytest runs.
