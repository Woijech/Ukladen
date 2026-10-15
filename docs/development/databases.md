# User Database Backend

Updated: 2026-10-15.
Status: P-05 is in progress. Database definition CRUD/trash/restore and internal
property-value validation/conversion rules are implemented. Property/record
persistence and HTTP operations and database views are not implemented yet.
This guide records each delivered increment separately.

## Database definitions

Migration `0014_user_databases` adds owner-scoped `workspace_databases`. Definitions
have name/color, optimistic metadata version, schema version, timestamps and trash
state. They do not own or delete page content. Schema version starts at 1; property
operations in the next increment will change it.

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

## Delivery order

Lifecycle selected under the owner's 2026-10-15 delegation: a page may participate
in several databases, sharing its body and keeping values per record. Databases,
properties and records will use recoverable trash. Parent database trash will hide
its contents without changing each child's independent trash state. Removing a
record never trashes its page. These persistence/API operations remain planned
until the corresponding increment is delivered.
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
