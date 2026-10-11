# Personal calendar API

Status: implemented, backend only — personal-event CRUD, official-event overrides,
resolved date-range reads, ownership/CSRF protection and safe structured diagnostics.
Free slots, conflict checking, task blocks, recurring/all-day personal events,
subject pages, nested notes, reminders and the calendar frontend are not implemented.

## Ownership and storage

`calendar` owns `personal_calendar_events` and `schedule_overrides`, introduced by
Alembic `0007_calendar`. Official occurrences remain shared facts owned by `schedule`.
Calendar application services read those facts through `ScheduleQueryService`; they
never call IIS, modify official occurrences or manufacture subject/room identifiers.

Personal events contain a UUID, owner UUID, title, description, timezone-aware start/end,
location, `blocks_time`, positive version and creation/update timestamps. Titles are
trimmed, required and limited to 200 characters. Locations are nullable, trimmed and
limited to 500 characters; an empty location is allowed. Descriptions preserve whitespace
and accept null or up to 10,000 characters. NUL characters are rejected in text inputs.
Start/end inputs must be ISO datetime strings containing `T` and an explicit UTC offset;
epoch numbers and naive times are rejected. End must be later than start in UTC.
Personal events may cross midnight and overlap; overlap does not prohibit saving.

An override is unique per `(user_id, official_event_id)`. It contains `hidden`, `skipped`,
nullable local title/description/location/time values, version and timestamps. Null local
values inherit the official representation; start/end must both be null or both supplied
with increasing UTC times. An empty description/location can clear the displayed value.
PostgreSQL enforces foreign keys, nonempty trimmed titles, valid intervals and positive
versions. Deleting a user cascades personal events and overrides, never official events.
Withdrawn official occurrences remain available for stored references.

Writes recheck and lock the active canonical user, sharing the existing academics/user
lock order. Services and repositories do not commit independently. Responses and success
logs follow transaction commit. Database errors, including commit failures, roll back
mutations and use the existing sanitized 503 handler.

## Endpoints

All paths below start with `/api/v1/calendar`. Every endpoint requires an active browser
session and returns `Cache-Control: no-store`. POST/PUT/PATCH/DELETE also require an
allowed exact Origin and the existing CSRF cookie plus `X-CSRF-Token` header.

| Method/path | Behavior |
| --- | --- |
| `GET /events?date_from=2026-10-05&date_to=2026-10-11` | Resolved personal calendar |
| `POST /personal-events` | Create an event; 201 with its stored representation |
| `GET /personal-events/{event_id}` | Read an owned event |
| `PATCH /personal-events/{event_id}` | Partially update an owned event |
| `DELETE /personal-events/{event_id}` | Remove an owned event; empty 204 |
| `GET /overrides?limit=100&offset=0` | Paginated owned overrides and source states |
| `PUT /overrides/{official_event_id}` | Create or fully replace a personal override; 200 |
| `DELETE /overrides/{official_event_id}` | Remove an owned override; empty 204 |

User IDs and other protected/unknown input fields are rejected. Missing and foreign
personal events produce the same 404. Removing a missing override also returns 404.
Request validation is 422, inactive/invalid sessions are 401, CSRF/Origin failure is 403,
and stale versions or inactive official sources for override writes are 409.

### Personal events

Example POST body:

```json
{
  "title": "Study OOP",
  "description": "Review the laboratory assignment",
  "starts_at": "2026-10-07T18:00:00+03:00",
  "ends_at": "2026-10-07T19:30:00+03:00",
  "location": "Home",
  "blocks_time": true
}
```

`description` and `location` default to null; `blocks_time` defaults to true. Responses
omit `user_id` and return the UUID, editable values, UTC timestamps and `version=1`.

PATCH requires `expected_version` equal to the returned version and at least one editable
field. An omitted field remains unchanged; explicit null clears only description/location.
The complete interval is validated after applying the patch, so changing only start/end
cannot produce an invalid event. Successful updates increment the version; stale versions
return 409 without changing the event. Re-read before retrying.

```json
{
  "expected_version": 1,
  "starts_at": "2026-10-07T19:00:00+03:00",
  "ends_at": "2026-10-07T20:30:00+03:00"
}
```

### Schedule overrides

The official UUID addresses an occurrence, not a recurring series. To create an override,
omit `expected_version` or supply 0. To replace one, send its current positive version.
Successful writes increment the version; mismatches are 409. Removing an override restores
the current official representation. A new override after removal starts at version 1.

```json
{
  "expected_version": 0,
  "hidden": false,
  "skipped": true,
  "description": "Personal attendance decision"
}
```

PUT replaces all editable fields: omitted flags become false and omitted local values
become null. Writes require a selected academic profile and an active occurrence in the
current group/subgroup, including whole-group events. No academic profile is 409;
unavailable/foreign-subgroup occurrences are 404. Listing/deletion remain available after
profile changes, including when no group is selected.

The list returns `{items: [{override: {...}, source_status: ...}], limit, offset}`. Limit is
1–200 and offset is nonnegative. Ordering is creation time descending, then official UUID.
`source_status` is `active`, `inactive_source`, or `outside_profile`. Historical overrides
are retained but do not resurrect inactive occurrences or reapply to a different group.
They are never automatically transferred to similar new UUIDs after an upstream date/label
change; see [schedule identity limits](schedule.md).

| State | Visible by default | Blocks time |
| --- | --- | --- |
| Ordinary lesson/exam | Yes | Yes |
| Hidden lesson/exam | No | Yes |
| Skipped lesson/exam | Yes, marked skipped | No |
| Hidden and skipped lesson/exam | No | No |
| Official announcement | Yes | No |
| Personal event | Yes | Its `blocks_time` value |

Announcement text is never interpreted as a cancellation instruction.

## Resolved reads and timezone

Both date parameters are required `YYYY-MM-DD` dates, inclusive in the user's stored
timezone. Numeric epoch values and datetime strings are rejected with 422.
At most 366 dates are accepted; unrepresentable boundaries and reversed ranges are rejected.
The exclusive end is midnight of the following local day, converted independently to UTC.
DST days therefore have their actual 23/25-hour length. Existing schedule HTTP endpoints
retain their inclusive Europe/Minsk date contract.

The response is `{events: [...], timezone, source, warnings}`. Resolved events contain:

- `id`: a UI identity such as `official:<uuid>` or `personal:<uuid>`;
- `source_event_id`: the UUID used for writes;
- `source`, `kind`, effective title/description/time/location and `blocks_time`;
- `hidden`, `skipped`, `has_override`, `version`;
- original official labels, group/subgroup, lesson type, note, rooms and teachers.

Personal versions are stored event versions. Official versions are the override version,
or 0 without an override. No subject ID or page link is invented. Original source details
remain accessible through the existing schedule-event endpoint.

`include_hidden=true` includes hidden occurrences. `source=official|personal` filters display
results. Reads select interval overlap, not only start dates; touching an exclusive boundary
does not overlap. Results sort by effective start and UI identity. Occurrences moved out
of the range are removed; moved-in occurrences are fetched by owned override references,
in a batch filtered by current group/subgroup.

Resolved reads and override listings use one caller-owned PostgreSQL REPEATABLE READ snapshot
across users, academics, calendar and schedule. Standalone schedule reads remain unchanged.

Without an academic profile, personal reads/CRUD work normally, `source` is null and warnings
contain `academic_profile_not_selected`. Otherwise existing source metadata is preserved.
Non-ready sources add `schedule_<status>`; a last successful import older than
`SCHEDULE_SYNC_INTERVAL_SECONDS` adds `schedule_stale`. Failed refreshes retain available
events. Empty results and `ready` never guarantee source coverage of arbitrary dates.

## Logging and verification

Existing middleware supplies route templates, status, duration and `X-Request-ID`.
Calendar records `calendar.resolved`, `calendar.personal_event_created`,
`calendar.personal_event_updated`, `calendar.personal_event_deleted`, `calendar.override_saved`,
`calendar.override_deleted` and warning-level `calendar.operation_rejected`. Metadata is limited
to user UUID, event count, source state and fixed rejection reason. Titles, descriptions,
locations, event UUIDs, input timestamps and request payloads are not logged. Failures use
`core.logging.log_failure` without exception messages or SQL parameters.

`test_calendar*.py` covers validation, timezone/DST, ownership, sessions, CSRF, partial
updates, concurrent/stale edits, database rollback, safe correlated logs, source refresh,
withdrawal, subgroups, moved occurrences, repeatable snapshots, schema constraints,
migration preservation and owner cascades. PostgreSQL/HTTP tests reuse
`AUTH_TEST_DATABASE_URL` / `AUTH_TEST_REDIS_URL` and isolated schemas. No test requires IIS.

Verification on 2026-10-12: Ruff, Ruff format, Pyright, `git diff --check` and
`docker compose config --quiet` passed. The full backend suite against disposable
PostgreSQL 18/pgvector and Redis 7.4 passed: 1056 tests, one skipped storage check.

Apply the backend version through the normal deployment process:

```bash
docker compose build api
docker compose run --rm migrate
docker compose up -d api worker beat
```

Downgrade removes calendar data while preserving users and official schedules. Do not use
deployment downgrade as a test. Implementation verification uses disposable services;
it does not apply this migration to the running application database.

## Compatibility with the original personal-event API

The original `/api/v1/calendar/events` POST and `/events/{event_id}` GET/PATCH/DELETE
contracts remain available, including `Location`, `is_busy`, nullable descriptions,
200-character titles, trimmed 4000-character write descriptions and partial PATCH.
The original `starts_at`/`ends_at` GET query returns the owned personal-event array
with the original half-open interval and 366-day limit. Date queries continue to
return the expanded resolved calendar. Mixing both query forms is rejected.

Both APIs use the same canonical event table. `is_busy` maps to `blocks_time`, and
legacy edits increment the canonical version while preserving location and other
modern fields. Writes serialize using the canonical active-user lock. The original
service/repository/domain compatibility code and its original tests are retained.
New clients should use the explicit versioned `/personal-events` contract.
