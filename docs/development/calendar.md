# Personal Calendar Event Persistence

Status: domain entity, SQLAlchemy model, Alembic migration and repository implemented.
Application services, HTTP endpoints and frontend: not implemented.

## Ownership and fields

`calendar/domain/events.py` defines the existing immutable `PersonalCalendarEvent`.
`calendar/infrastructure/orm.py` maps it to `personal_calendar_events`:

| Field | Storage |
| --- | --- |
| `id` | UUID primary key |
| `user_id` | Required FK to `users.id`, cascade on user deletion |
| `title` | Required text containing a non-whitespace character |
| `description` | Nullable text |
| `starts_at`, `ends_at` | Required timezone-aware timestamps; end must follow start |
| `is_busy` | Required boolean, database default true |
| `created_at`, `updated_at` | Required timezone-aware timestamps, database default current time |

The entity rejects blank titles, naive timestamps and non-positive intervals.
PostgreSQL additionally enforces a nonblank title and a positive interval.
The repository returns timestamps normalized to UTC. The database stores instants,
not a recurring event timezone. All-day events and recurrence are not implemented.

## Repository contract

`PersonalCalendarEventRepository` is an application-owned port in
`calendar/application/ports.py`. Its SQLAlchemy adapter takes the caller's
synchronous `Session`. It never commits or rolls back independently.

Every method requires a trusted `user_id`, which future application/HTTP callers
must obtain from the authenticated session rather than request data:

| Method | Behavior |
| --- | --- |
| `create(user_id, event)` | Validates that `event.user_id` matches the owner, inserts and returns a domain entity. Duplicate IDs fail rather than overwriting an event. |
| `get(user_id, event_id)` | Returns an owned event; missing and foreign events both return null. |
| `list_for_period(user_id, starts_at, ends_at)` | Returns owned events overlapping the half-open period, ordered by start then UUID. |
| `update(user_id, event)` | Replaces title, description, interval and busy flag of an owned event. Preserves ID, owner and creation time; sets update time from the database clock. Missing and foreign events return null. |
| `delete(user_id, event_id)` | Deletes only an owned event; returns false for both missing and foreign events. |

Creation and update reject a mismatched entity owner before executing SQL. Each
lookup, update and deletion includes ownership in its SQL predicate. Ownership
scoping is not a substitute for session authentication or active-user checks;
those application/HTTP services are not implemented in this slice.

Updates replace all mutable fields. They are not partial patches and do not
implement optimistic concurrency control. Future PATCH services must define
their concurrency behavior before exposing this operation to clients.

Period bounds must be timezone-aware and have a positive duration, compared as
UTC instants. An event overlaps when `event.starts_at < ends_at` and
`event.ends_at > starts_at`. Events spanning the period are included; events
ending exactly at its start or starting exactly at its end are excluded. Both
busy and non-busy events are returned. An index on `(user_id, starts_at, id)`
supports owner-scoped ordered reads. Reads refresh SQLAlchemy's identity map so
reusing a session does not return stale cached fields.

## Migration and verification

`0006_personal_calendar_events` follows `0005_academics_profile` and creates only
the event table, its constraints and index. Existing users, auth and academic
profiles are preserved. Alembic imports the calendar ORM for metadata comparison.
Downgrade removes the table and its events; unrelated tables remain intact.

Use the existing migration command after configuring the development environment:

```bash
cd apps/backend
uv run --env-file ../../.env alembic upgrade head
```

`tests/test_calendar_persistence.py` covers migration round trips and metadata
agreement, owner-scoped CRUD, duplicate IDs, period boundaries, UTC conversion,
rollback, independent-session persistence, identity-map refresh, database
constraints and cascading deletion. It uses the existing isolated PostgreSQL
fixtures and requires `AUTH_TEST_DATABASE_URL`; it skips if that variable is unset.
`tests/test_calendar_repository.py` checks invalid ranges, including a reversed
UTC interval at a DST transition, without database access.

Official schedule persistence/synchronization, calendar resolution, schedule
overrides, conflicts, free slots and task blocks: not implemented.
