# User Database Backend

Updated: 2026-10-15.
Status: P-05 is in progress. Database/property/page-backed record APIs, recoverable
trash and typed value validation/conversions are implemented. Saved table/calendar
database views and date projection are not implemented yet.
This guide records each delivered increment separately.

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
end. A missing end means a single date or instant. Calendar projection is not
implemented yet; these values do not reserve busy time.

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
an active page. Future table/calendar content queries will omit trashed pages.
Multi-module reads use one repeatable-read snapshot.

`GET /api/v1/workspace/pages/{page_id}/database-records` lists a page's active records
in active databases with bounded pagination. Clients can retrieve each referenced
database's property definitions to display values above the shared page body.
No nesting, collection or event link creates records implicitly.

Migration downgrade refuses while properties or records exist, including trash.
Empty-table round trips preserve page content. No permanent-delete API is exposed.

## Delivery order

Lifecycle selected under the owner's 2026-10-15 delegation: a page may participate
in several databases, sharing its body and keeping values per record. Databases,
properties and records use recoverable trash. Parent database trash hides
its contents without changing each child's independent trash state. Removing a
record never trashes its page. These persistence/API operations are implemented;
saved database views and calendar projection remain planned.
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
