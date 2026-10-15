# User Database Backend

Updated: 2026-10-15.
Status: P-05 is in progress. Property-value validation and safe conversion rules
are implemented internally. Persistence, HTTP operations and database views are
not implemented yet. This guide records each delivered increment separately.

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
The planned persistence/version/lifecycle contract is recorded in
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
