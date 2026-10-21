# User Database Backend

Updated: 2026-10-22.
Status: P-05 backend is implemented: database/property/page-backed record APIs,
recoverable trash, typed validation/conversions, table/calendar views, date moves
and mixed display with official/personal events.
This guide records each backend increment separately. Schema/record and saved table
and day/week/month calendar UI are described in the [frontend guide](../architecture/frontend.md).
Mixed display and drag date moves remain API-only.

## Database definitions

Migration `0014_user_databases` adds owner-scoped `workspace_databases`. Definitions
have name/color, optimistic metadata version, schema version, timestamps and trash
state. They do not own or delete page content. Schema version starts at 1; every
property creation, edit, trash and restore increments it and the database version.

Routes under `/api/v1/workspace/databases`:

| Method | Suffix | Behavior |
| --- | --- | --- |
| POST | empty | Create with name and optional color |
| GET | empty | List active definitions; `trashed=true` lists trash |
| GET | `/{id}` | Read owned metadata, including trash |
| PATCH | `/{id}` | Edit name/color with `expected_version` |
| POST | `/{id}/trash` | Recoverable removal with `expected_version` |
| POST | `/{id}/restore` | Restore with `expected_version` |

Lists use limit 1–200 (default 100), nonnegative bounded offset and creation/UUID
order. Names/colors, omitted/null PATCH semantics, sessions, CSRF and safe ownership
errors reuse organization contracts. Writes recheck/lock the canonical active owner.
Stale versions, editing trash and invalid lifecycle transitions return 409.
Responses omit owner IDs and use no-store. Downgrade refuses while any database
definitions exist; an empty-table round trip preserves existing pages and events.

## Property rules

Supported initial kinds are `text`, `number`, `checkbox`, `select`, `multi_select`,
`url` and `date`. Property and option names use trimmed 1–100 character names.
Options have stable UUIDs, at most 100 per property; IDs and case-insensitive labels
must be unique within a property. Options belong only to select kinds.

Text preserves whitespace and is limited to 10000 characters, without NUL or
invalid Unicode. Numbers are finite JSON numbers in the JavaScript-safe integer
range; booleans and numeric strings are rejected. Checkboxes require a real boolean.
HTTP/HTTPS URLs use the same stored-link validation as page blocks, with a 2048
character limit and no credentials, whitespace or control characters. No URL is fetched.

Select values identify defined option UUIDs; multi-select values contain at most
100 distinct option UUIDs. Renaming an option keeps selected values intact. Null
means an unset property, while false, zero and empty text remain actual values.

Dates are discriminated objects: `{"kind":"date","start":"2026-10-20","end":null}`
or `{"kind":"datetime","start":"2026-10-20T12:00:00+03:00","end":null}`.
Date-only values retain their date, including inclusive optional end dates. Timed
values require explicit offsets, normalize to UTC and have a strictly later optional
end. A missing end means a single date or instant. Calendar projection preserves
these values; they do not reserve busy time.

Safe conversions support text/URL after URL validation and select/multi-select
when no selected option is lost. Other populated type changes, removal of used
options and multi-select-to-select with several values fail with a conflict.
Unset values may change type. Application operations must validate every stored
value, including recoverable records, before committing any schema conversion.

## Property and record operations

Migration `0015_database_content` adds relational property definitions and page-backed
records. Composite foreign keys enforce the database owner and page owner. A page
may have one record per database, including trash, and may participate in several
databases. Re-adding a trashed membership returns 409; restore the existing record.
Values use stable property UUID keys and belong to the record, not the page body.

Routes under `/api/v1/workspace/databases/{database_id}`:

| Method | Suffix | Behavior |
| --- | --- | --- |
| POST | `/properties` | Create name/kind/options with `expected_schema_version` |
| GET | `/properties` | List active definitions in position/UUID order, with current schema version |
| GET | `/properties/{id}` | Read a definition, including trash |
| PATCH | `/properties/{id}` | Edit supplied name/kind/options/position with property and schema versions |
| POST | `/properties/{id}/trash` or `/restore` | Preserve or recover the property and all values |
| POST | `/records` | Add an owned `page_id` or create an empty page with `title`; supply values/schema version |
| GET | `/records` | List active record references and current page summaries |
| GET | `/records/{id}` | Read values, page summary and current schema version |
| PATCH | `/records/{id}` | Partially update values with record and schema versions |
| POST | `/records/{id}/trash` or `/restore` | Preserve/recover membership without trashing the page |

Property lifecycle bodies include `expected_version` and `expected_schema_version`.
Record lifecycle bodies require `expected_version`. Lists accept `trashed=true` to
inspect independently trashed children; record lists use standard bounded pagination.
Property creation appends a column, while PATCH can set a position from 0–100000.
Option IDs are generated when omitted on creation; retain returned IDs when renaming
options. Options replace the whole list atomically.

Record creation requires exactly one of `page_id` or `title`. New-page creation,
value validation and record insertion share one transaction, so failures leave no
orphan page. Record responses contain `record`, `page` metadata and `schema_version`,
without page bodies or owner IDs. Membership page IDs are immutable. Edit page title/
content through the existing notes API and its page version.

Value PATCH preserves omitted keys; null clears a value. Unknown, foreign, trashed
or wrong-database property IDs are rejected. Each record retains at most 100 values
and 128 KiB of normalized UTF-8 JSON. Each database supports at most 100 property
definitions and 10000 records, including trash. Trash occupies these limits until
a separately requested permanent-purge policy exists.

All value writes check the current schema version. Schema conversions validate
active and trashed record values before any mutation, update converted record
versions and commit all changes atomically. Renaming preserves property/option IDs.
Normal record responses hide trashed-property values while preserving them in
storage; unrelated value edits retain them. Restoring a property reveals them again.

Database trash hides operations on its contents with 409 and preserves each child's
independent state. Restore the database before restoring/editing children. Record
reference reads retain page trash metadata; adding/editing/restoring a record requires
an active page. Table content queries omit trashed pages before pagination;
calendar projection also omits trashed pages.
Multi-module reads use one repeatable-read snapshot.

`GET /api/v1/workspace/pages/{page_id}/database-records` lists a page's active records
in active databases with bounded pagination. Clients can retrieve each referenced
database's property definitions to display values above the shared page body.
No nesting, collection or event link creates records implicitly.

Migration downgrade refuses while properties or records exist, including trash.
Empty-table round trips preserve page content. No permanent-delete API is exposed.

## Saved table views

Migration `0016_database_table_views` adds saved owner/database-scoped settings.
Routes under `/api/v1/workspace/databases/{database_id}/views`:

| Method | Suffix | Behavior |
| --- | --- | --- |
| POST | empty | Create name/color/query with `expected_schema_version` |
| GET | empty | List saved definitions with bounded pagination |
| GET | `/{id}` | Read settings, including references needing repair |
| PATCH | `/{id}` | Edit supplied name/color/query with view/schema versions |
| DELETE | `/{id}?expected_version=N` | Remove settings only |
| GET | `/{id}/records` | Return selected properties, matching records, schema version and total/limit/offset |

The default layout is `table`; calendar views reuse the same query contract. Query settings have strict integer `version: 1`, at most
100 column IDs, 20 AND-combined filters and 3 distinct sort fields, within 64 KiB.
`columns: null` automatically shows all active properties in their schema order;
an explicit list fixes order/selection, and `[]` produces title-only rows. The page
title remains in each page summary. Returned values include only displayed columns;
filters may reference other active columns. Omitted query fields use empty filters/
sorts and automatic columns. PATCH replaces the whole query object atomically.

Filters identify stable property UUIDs and allow only typed operations:

- `eq`/`neq` compare scalar values or an entire normalized date/date-range value.
  `neq` also includes unset values. Multi-select uses `contains` instead of equality.
- `contains` searches text literally and case-sensitively, including literal `%`/`_`,
  or checks one valid option UUID in a multi-select field.
- `gt`/`gte`/`lt`/`lte` compare numbers or date starts. Date comparisons match the
  supplied date kind; date-only comparisons do not guess a timezone for timed values.
- `is_empty`/`is_not_empty` distinguish missing/null/empty text/empty selections
  from meaningful false and zero values. These operators take no value.

Sorts are ascending/descending over scalar fields; select sorts follow configured
option order, dates use canonical start values, and unset values always sort last.
Multi-select sorting is rejected. Creation time/UUID break ties deterministically.
Property/option renaming preserves filters. Unknown/trashed properties, incompatible
changed types and removed selected options fail validation rather than weakening
the query. Saved query reads return 409 until repaired; definition GET/DELETE remain
available and PATCH can replace the query using the current schema version.

SQL filters/sorts use bound SQLAlchemy expressions in workspace infrastructure.
Only matching record/page IDs are collected, with the existing 10000-record limit;
page metadata is fetched through a bounded notes application query without bodies.
Page trash is excluded before applying offset/limit, then only selected record
values are loaded. This keeps pagination/total correct without crossing into notes
ORM from workspace. The entire read shares one repeatable-read snapshot.

View operations use normal active-owner/session/CSRF/version rules. Deleting a view
preserves records, schemas, pages and event busy state. Database trash requires
restoring the database before querying its views. Migration downgrade refuses to
drop retained view settings; empty-table round trips preserve canonical content.

## Date-bound calendar views

Migration `0017_database_calendar_views` adds calendar layout and an owned composite
foreign key to the chosen property. Create a view with `layout: "calendar"`, an
explicit active `date_property_id` and optional `calendar_layout` (`day`, `week`,
`month`, default `week`). A table has neither calendar field. Layout kind is immutable;
create another view over the same records for a different layout. PATCH may change
binding or calendar preference with view/schema versions. Property renaming preserves
binding; trash or incompatible type changes require explicit repair (409 on query).

`GET /api/v1/workspace/databases/{database_id}/views/{view_id}/entries` takes
`date_from`/`date_to` inclusive dates, covering at most 366 days in the current user
profile timezone. It applies saved filters/sorts and excludes undated, trashed record,
page and database content. Date-only values retain inclusive date ends. Timed ranges
use half-open overlap; a missing end is an instant, including the start of the window
and excluding its end. DST boundaries follow the user's IANA timezone.

Entries retain a discriminated date payload and `source: "record_date"`, with
`blocks_time: false`. Identity is `record_date:{record_id}:{property_id}`. The entry
carries database, page, record and property IDs plus record/schema versions, without
page body or unrelated values. SQL loads only matching references and the bound date;
notes metadata and workspace values share one repeatable-read snapshot.

`PATCH .../views/{view_id}/entries/{record_id}` accepts `property_id`, `date`,
`expected_version` (record) and `expected_schema_version`. It rechecks the current
binding under the owner lock and delegates to the normal record-value operation.
A stale binding cannot move a different property. Page content and personal events
are untouched; projection never creates an event or reserves time. Clear a date with
the ordinary record PATCH. Table queries on calendar views return 409.

Downgrade to 0016 refuses retained calendar views. Table-only settings survive the
column removal and upgrade without changes.

## Mixed calendar display

`GET /api/v1/calendar/display?date_from=2026-10-01&date_to=2026-10-31` returns
`entries`, `timezone`, schedule `source` state and `warnings`. Optional repeated
`database_view_ids` selects up to 20 distinct owned database calendar views.
`include_hidden` and `source=official|personal` apply to event selection, using the
unchanged calendar resolver. Record selection comes from each chosen view's query.
A missing, foreign, trashed-parent or invalid requested view fails the whole request;
no source is silently omitted. No selected database views produces the event-only set.

Entries discriminate `source: official|personal|record_date`. Event fields/identities,
overrides, hidden/skipped/busy state and source diagnostics are preserved. Record-date
entries retain their typed date and write IDs, always nonblocking. The same record/
property selected by multiple views appears once; different date properties remain
separate. At most 10000 distinct record-date entries are returned; larger selections
are rejected without partial results. Events retain chronological order first, then
record entries follow selected-view/query order. Clients place date and timed entries
using their discriminated payloads rather than relying on a global midnight timestamp.

The calendar application composes through its own `RecordCalendarQuery` port, with a
workspace application implementation wired at presentation. All sources share a
repeatable-read transaction. Existing `/calendar/events`, legacy timestamp reads and
P-03 event-view APIs are unchanged. This display is not an availability query.

## Delivery order

Lifecycle selected under the owner's 2026-10-15 delegation: a page may participate
in several databases, sharing its body and keeping values per record. Databases,
properties and records use recoverable trash. Parent database trash hides
its contents without changing each child's independent trash state. Removing a
record never trashes its page. These persistence/API operations are implemented;
saved table/calendar views, date projection and mixed display are also implemented.
The persistence/version/lifecycle contract is recorded in
[ADR 0007](../adr/0007-use-page-backed-database-records.md).

1. Internal property/date validation and conversion rules, with unit tests.
2. Owner-scoped database, property and page-backed record persistence and APIs.
3. Saved table views, bounded typed filters, sorting and visible-column settings.
4. Explicit date-bound calendar views and compatible mixed calendar projection.

Each increment is verified and committed locally. Frontend UI, formulas,
collaboration and typed task planning are outside P-05.

## Verification history

2026-10-15, property rules increment: Ruff, Ruff format, Pyright and Compose
configuration passed. Property/block unit checks passed (100 tests), and the full
backend suite with disposable PostgreSQL/Redis passed: 1303 passed, 1 optional
native S3 avatar test skipped. Database persistence and view APIs were not part of
this increment. No running-stack migration, frontend work, deployment or push.

2026-10-15, database definition increment: Ruff, Ruff format, Pyright and Compose
configuration passed. Native database/workspace/calendar-view compatibility checks
passed (48 tests), including migration metadata/round trips, refused destructive
downgrade, isolation, versions, rollback and trash/restore. The full-suite result
above belongs to the earlier increment and was not rerun for this metadata-only step.

2026-10-15, property/record increment: Ruff, Ruff format, Pyright and Compose
configuration passed. Native database/workspace checks passed (29 tests), including
SQL ownership constraints, preserving/refused downgrades, retained trash values,
schema conversion rollback, shared-page membership, schema concurrency, page/record
snapshot reads and value limits. The final service version guard was rechecked by
the 11 property/record HTTP/persistence tests. Table/calendar views remain planned.

2026-10-15, saved table-view increment: Ruff, Ruff format, Pyright and Compose
configuration passed. Database/query/notes compatibility checks passed (113 tests),
including typed filters, literal text matching, stable sorting, page-trash-aware
pagination, one-snapshot metadata reads, permissions, SQL constraints, query version
checks and preserving/refused downgrades. Calendar database views/projection remain
planned. No frontend changes, running-stack migration, deployment or push.

2026-10-15, date-bound calendar increment: Ruff, Ruff format, Pyright and Compose
configuration passed. Native calendar/table/migration checks passed (12 tests),
including DST overlap, date-only ranges, instant/interval boundaries, schema/record/
binding conflicts, owner/CSRF checks, trash and preserving/refused downgrades.
Mixed display composition is not implemented in this increment.

2026-10-15, completed P-05/mixed display increment: Ruff, Ruff format, Pyright and
`docker compose --env-file .env.example config --quiet` passed. Mixed display/database/
event-view checks passed (30 tests). The full backend suite passed against disposable
PostgreSQL/pgvector and Redis: **1345 passed, 1 optional native S3 avatar test skipped**.
No test calls real IIS or an LLM. Existing Starlette TestClient/Alembic deprecation
warnings remain. Local documentation links and `git diff --check` passed.
The slice uses migrations 0014–0017; no running-stack database was migrated.
Frontend checks are not applicable because this slice changes no frontend code.
No frontend UI, P-06 planning, deployment or push is included.
