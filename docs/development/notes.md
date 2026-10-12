# Notes Backend

Updated: 2026-10-12.
Status: implemented, backend only. Blocks, editor UI, user databases, sharing,
permanent deletion, revision history and export are not implemented.

## Content and ownership

A page is an independent user-owned object, optionally nested under another page.
Any page can act as a group of child notes. No academic profile, subject or event is
required. The current document is Markdown (`content_format: markdown`,
`content_format_version: 1`); it is not a block document. Titles are trimmed and
limited to 1–200 characters; content allows 0–100000 characters. NUL is rejected.
HTML rendering/sanitization is a future client responsibility; the API returns text.

`notes` owns hierarchy, body, version and trash. Writes lock the canonical active
user in the caller-owned transaction, preventing concurrent hierarchy cycles.
Composite foreign keys prevent cross-owner parents; moves preserve page identity.

## API

All endpoints require a browser session, return `Cache-Control: no-store`, and
write operations require the existing CSRF/Origin checks. Owner IDs are not accepted.

| Method | Path | Behavior |
| --- | --- | --- |
| POST | `/api/v1/notes/pages` | Create with `title`, optional `content` and `parent_id` |
| GET | `/api/v1/notes/pages` | Paginated summaries; no bodies |
| GET | `/api/v1/notes/pages/{id}` | Owned page including body and trash state |
| PATCH | `/api/v1/notes/pages/{id}` | Update supplied fields with `expected_version` |
| POST | `/api/v1/notes/pages/{id}/trash` | Trash branch with `expected_version` |
| POST | `/api/v1/notes/pages/{id}/restore` | Restore trash batch with `expected_version` |

Lists default to active pages; `trashed=true` selects trash. `parent_id` selects
immediate children; `roots_only=true` selects roots. Combining these two filters
is invalid. `limit` defaults to 100 (1–200), `offset` to 0, ordered by creation/UUID.
Patch omission preserves values; `parent_id: null` moves to root; title/content
cannot be null. An empty body is allowed. Stale versions, cycles, and edits/moves
of trashed pages return 409. Missing/foreign pages return the same 404.

## Recoverable branch trash

Trashing a page marks its currently active descendants in one batch and increments
each affected version. Content and IDs are retained. Previously trashed descendants
keep their own batches. Restore the batch root identified by `trash_batch_id`;
individual descendants cannot be restored out of that batch. The root's parent must
be active before restoration. Restoring a group does not resurrect independently
trashed children. There is no public hard-delete operation or automatic purge.

Migration `0008_note_pages` adds `note_pages`; owner deletion cascades at storage
level. Upgrade/downgrade and metadata checks use disposable test databases only.

## Verification

HTTP/database tests cover independent creation, nesting/moves, concurrent cycle
prevention, subtree trash/restore, stale versions, validation, sessions/CSRF,
cross-owner access, rollback/private logs, constraints and migration round trips.
