# Official schedule storage

Status: dated expansion and PostgreSQL storage implemented. Background synchronization
and persisted-event HTTP endpoints: not implemented yet.

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
