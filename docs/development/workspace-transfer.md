# Personal page and database transfer

Implemented locally on 2026-11-23; not deployed to the running stack.

The portable JSON format transfers owned pages (including trash), native documents,
databases, retained properties/record values, relations, calculations and saved
views. Import creates new identities and places root pages beneath a new import
page. Existing objects are never overwritten. Literal text and HTTP links are not
rewritten; typed UUID references are remapped.

This transfer excludes binary materials/attachments, event/task links, calendars,
tasks, collections/tags, revisions, AI chats, credentials and account settings.
Use the full PostgreSQL/object-storage backup for complete recovery.

Endpoints under `/api/v1/workspace/transfer`: authenticated GET `/export`, CSRF
POST `/preview` and POST `/import`. Preview executes the same bounded application
operation in a rolled-back savepoint; it persists no imported objects. Import
requires the digest of the exact archive, destination title and current owner.
All import writes commit together or roll back together.
Migration `0049_workspace_transfer` stores owner-scoped import receipts in
PostgreSQL. Retrying the same archive/title returns the same import root. To make
another copy deliberately, choose a different destination title. Receipts do not
contain page bodies. New identities, timestamps and versions are assigned on import.

Limits: 32 MiB JSON, 1000 pages, 100 databases, 10000 records, 1000 saved views,
100 properties per database and page hierarchy depth 64. Oversized exports fail
explicitly instead of truncating. Invalid references/configurations fail preview;
unavailable view references must be repaired or removed before portable import.
Independent page trash batches are preserved. Timestamps and versions start anew.
No remote URLs, files or language models are invoked by transfer.

The settings panel exposes **Download JSON**, then file selection, a destination
title, **Check file** and explicit **Create copy**. Changing the title invalidates
the preview. Navigation is blocked while a request is in flight. Export files
contain private page and property content; store them with the same care as notes.

Verification: three pure format/hierarchy/digest tests and four PostgreSQL/Redis
HTTP scenarios passed, including cross-owner roundtrip, fresh typed references,
calculation results, independent trash batches, retained hidden property values,
trashed relation targets, no preview residue, retry safety, CSRF and atomic rollback.
A CLI browser scenario verified downloading, no premature writes, invalidating a
preview on title change, explicit import and a contained 390px confirmation dialog.
The full 2170-case backend collection (partitioned native runs), all 356 existing
frontend cases, lint/type checks and production build were also checked in this delivery.
