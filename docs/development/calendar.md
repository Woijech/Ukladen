# Personal Calendar Event Persistence and API

Status: domain entity, SQLAlchemy model, Alembic migration, application service and
owner-scoped HTTP endpoints implemented.
Personal calendar resolution, schedule persistence/synchronization, schedule
overrides, conflicts, free slots and task blocks: not implemented.

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

## HTTP API

`calendar/presentation/routes.py` exposes `/api/v1/calendar/events` with an
authenticated session, `Cache-Control: no-store` and the existing Origin/CSRF
protection on `POST`, `PATCH` and `DELETE`. All routes require an active
canonical user; a disabled or missing user receives the existing authenticated
401 response with cookie clearing.

`PersonalEventService` (`calendar/application/service.py`) performs the use-case
rules inside caller-owned transactions. Only the session owner's UUID is used:
request bodies, paths and query parameters can never select another user. The
service enforces the domain rules, treats missing and foreign events as the same
404 and delegates persistence to the owner-scoped repository. It never commits.

| Method | Path | Behavior |
| --- | --- | --- |
| `GET` | `/api/v1/calendar/events` | Lists owned events overlapping `[starts_at, ends_at)` from required `starts_at`/`ends_at` timezone-aware query parameters. Period length is limited to 366 days. |
| `POST` | `/api/v1/calendar/events` | Creates an event; generates the UUID and timestamps in the service; returns 201 with a `Location` header. |
| `GET` | `/api/v1/calendar/events/{event_id}` | Returns one owned event, or 404 for missing and foreign events. |
| `PATCH` | `/api/v1/calendar/events/{event_id}` | Partial update of the supplied editable fields; omitted fields keep their current values, an explicit null description clears it. Empty patches are rejected with 422. |
| `DELETE` | `/api/v1/calendar/events/{event_id}` | Deletes an owned event; returns 204, or 404 for missing and foreign events. |

Request/response DTOs (`calendar/presentation/schemas.py`) reject extra fields and
return the stored entity without the internal `user_id`. Validation failures map
to 422 `Invalid calendar event.`, missing events to 404 `Calendar event not
found.`, and unexpected repository failures to the sanitized 503.

Domain-level limits: the title is trimmed, non-blank and at most 200 characters;
the description is trimmed and at most 4000 characters, with a blank description
stored as null. Timestamps must be timezone-aware and the end must follow the
start. `is_busy` defaults to true. PATCH is a partial update by design, unlike
the repository's full-row replacement, so clients cannot unintentionally clear
omitted fields. Optimistic concurrency control is not implemented; updates read
and replace within one route transaction.

All-day events and recurrence are not implemented.

Tests: `tests/test_calendar_service.py` covers domain rules, owner scoping and
the partial-update semantics with mocked ports. `tests/test_calendar_http.py`
covers authentication, CSRF, ownership 404s, transport/patch validation,
`no-store`, 201/204 responses, the `Location` header and the OpenAPI contract
using the existing authenticated HTTP fixtures.

Official schedule persistence/synchronization, calendar resolution, schedule
overrides, conflicts, free slots and task blocks: not implemented.
