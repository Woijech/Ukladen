# Notes Backend

Updated: 2026-10-28.
Status: implemented: independent nested pages, versioned block documents
and recoverable trash. The page tree and block editor UI are described in the
[frontend guide](../architecture/frontend.md). Sharing, permanent deletion, revision history and
export are not implemented. Page-backed user databases reference these pages through
notes application services; see [database contracts](databases.md).

## Content and ownership

A page is an independent user-owned object, optionally nested under another page.
Any page can act as a group of child notes. No academic profile, subject or event is
required. The authoritative body is a JSONB document with `schema_version: 1` and
an ordered `blocks` array. Page detail also returns a derived Markdown `content`
(`content_format: markdown`, `content_format_version: 1`) for existing readers;
it is not a second editable copy. Titles are trimmed and limited to 1–200 characters.
NUL and invalid Unicode are rejected. HTML rendering/sanitization is a future
client responsibility; the API returns structured data and text.

`notes` owns hierarchy, body, version and trash. Writes lock the canonical active
user in the caller-owned transaction, preventing concurrent hierarchy cycles.
Composite foreign keys prevent cross-owner parents; moves preserve page identity.

## API

All endpoints require a browser session, return `Cache-Control: no-store`, and
write operations require the existing CSRF/Origin checks. Owner IDs are not accepted.

| Method | Path | Behavior |
| --- | --- | --- |
| POST | `/api/v1/notes/pages` | Create with `title`, optional `parent_id` and either `content` or `document` |
| GET | `/api/v1/notes/pages` | Paginated summaries; no bodies |
| GET | `/api/v1/notes/pages/{id}` | Owned page including body and trash state |
| PATCH | `/api/v1/notes/pages/{id}` | Update supplied fields with `expected_version` |
| GET | `/api/v1/notes/pages/{id}/document` | Read `page_id`, page `version` and canonical `document` |
| PUT | `/api/v1/notes/pages/{id}/document` | Replace document atomically with `expected_version` |
| POST | `/api/v1/notes/pages/{id}/trash` | Trash branch with `expected_version` |
| POST | `/api/v1/notes/pages/{id}/restore` | Restore trash batch with `expected_version` |

Lists default to active pages; `trashed=true` selects trash. `parent_id` selects
immediate children; `roots_only=true` selects roots. Combining these two filters
is invalid. `limit` defaults to 100 (1–200), `offset` to 0, ordered by creation/UUID.
Patch omission preserves values; `parent_id: null` moves to root; title/content
cannot be null. An empty body is allowed. Creation rejects explicit `document: null`
and requests supplying both `content` and `document`, even if content is empty.
Stale versions, cycles, and edits/moves of trashed pages return 409.
Missing/foreign pages return the same 404. Invalid documents return 422.

## Block document contract

Requests must supply both `schema_version` and `blocks`. Each block has a
client-supplied UUID `id`, unique within its document, and a `type`.
Preserve IDs when editing or reordering; assign new UUIDs to new blocks. Array order
is display order. A PUT replaces the entire document: omitted blocks are removed,
and an empty array clears the body. There are no separate block endpoints.

| Type | Fields besides `id` and `type` |
| --- | --- |
| `text` | `text`; `text_format`: `plain` (default) or `markdown` |
| `heading` | Single-line `text`; strict integer `level` from 1 to 6 |
| `list` | 1–1000 single-line string `items`; `style`: `bulleted` (default) or `numbered` |
| `checkbox` | Single-line `text`; strict boolean `checked` (default false) |
| `link` | Single-line `text`; absolute HTTP/HTTPS `url` up to 2048 characters |

Unknown fields/types, duplicate IDs, coercible booleans/numbers, unsafe URLs,
credentials in URLs and control/whitespace characters in URLs are rejected.
Text blocks may contain newlines. Documents allow at most 1000 blocks, 100000
aggregate text/list-item/URL characters and 1 MiB of normalized UTF-8 JSON, including
field names and JSON spacing. The database checks the envelope, block count and
size; domain validation checks every payload. Lists and blocks are flat; nested
blocks, inline rich formatting and material references are not implemented.

Example document replacement:

```json
{
  "expected_version": 1,
  "document": {
    "schema_version": 1,
    "blocks": [
      {"id": "ac851fac-a22a-4b2a-8a42-8e0b2a26ef5c", "type": "heading", "text": "Chest", "level": 2},
      {"id": "b0d36793-c494-42fc-9bfa-a192c924229b", "type": "checkbox", "text": "Warm up", "checked": false}
    ]
  }
}
```

Document and metadata mutations share one page version. A successful PUT increments
that version; after 409, reload the page/document and reconcile before saving again.
Trashed documents remain readable but cannot be edited. Summaries and calendar
backlinks do not fetch document bodies.

## Markdown compatibility and migration

Existing Markdown is preserved verbatim in one `text` block with
`text_format: markdown` and the page UUID as its block ID; empty content becomes an empty array.
No automatic Markdown parsing is attempted. Legacy PATCH `content` works only on
empty documents or a single Markdown text block, preserving an existing block ID.
It returns 409 for structured documents instead of flattening them. PATCH title/parent
continues to work on any document. Structured content has a derived Markdown
projection; plain text is escaped, while Markdown text remains verbatim.

Migration `0010_page_block_documents` replaces the old content column and preserves
page identities, owners, hierarchy, versions, timestamps, trash batches and links.
Run it with the existing Alembic deployment workflow before using the new backend.
A downgrade to `0009_page_calendar_links` is allowed only for empty documents or
nonempty legacy Markdown wrappers whose block ID equals the page ID. It refuses
structured documents, custom IDs and empty text blocks before changing the schema.
Back up data and resolve those documents explicitly before attempting such a rollback.

## Recoverable branch trash

Trashing a page marks its currently active descendants in one batch and increments
each affected version. Content and IDs are retained. Previously trashed descendants
keep their own batches. Restore the batch root identified by `trash_batch_id`;
individual descendants cannot be restored out of that batch. The root's parent must
be active before restoration. Restoring a group does not resurrect independently
trashed children. There is no public hard-delete operation or automatic purge.

Migration `0008_note_pages` adds `note_pages`; owner deletion cascades at storage
level. Upgrade/downgrade and metadata checks use disposable test databases only.

Optional links to personal/official events and creation from an event are implemented
through [relations](relations.md). Links can target any page, including a group root.

## Verification

HTTP/database tests cover independent creation, nesting/moves, concurrent cycle
prevention, subtree trash/restore, stale versions, validation, sessions/CSRF,
cross-owner access, rollback/private logs, constraints and migration round trips.
Block tests additionally cover typed payloads, stable IDs, ordered replacement,
duplicate IDs, size/Unicode/URL limits, legacy overwrite protection, concurrent
document/metadata saves, event-based creation, summary queries without bodies,
preserving old-page migration and refused destructive downgrade.

Verified on 2026-10-12: full backend pytest with disposable PostgreSQL/Redis —
1164 passed, 1 S3 avatar-storage test skipped. Ruff, Ruff format, Pyright,
`docker compose config`, local documentation links and diff checks passed.
No frontend changes or running-stack migration/deployment were performed.


## Page workspace UI (2026-10-28)

Implemented on the existing API: a nested, collapsible page list alongside a quiet
page canvas, ancestor breadcrumbs, root/child creation and page actions. The client
fetches summary batches of 200 until complete before assembling the hierarchy; it
never presents one API batch as a complete tree or a global search. Bodies load only
for the selected page. The tree becomes a collapsible compact list on narrow screens.
Creation asks for a nonblank title and opens the created page with title focus.
A private `/workspace?page=<UUID>` link opens that page through normal session and
ownership checks; copying a link does not grant another account access.

One searchable block picker serves `/` in an empty paragraph, the trailing writing
line and insertion buttons. Arrow keys, Enter and Escape work from the search field.
Available types are text, headings H1–H6, bulleted/numbered lists, checkboxes and links.
Plain paragraphs split on Enter; Shift+Enter inserts a newline. Existing Markdown
wrappers retain their source and format. Lists render native markers and add items
with Enter; Backspace removes an empty item while retaining at least one item.
Native drag handles and explicit up/down actions reorder the same UUIDs. Deleting
a block requires confirmation. Safe conversion is limited to single-line plain text
and headings, heading levels, and list styles; structured values and Markdown are
not silently flattened.

Saves remain manual, including Ctrl/Cmd+S, with compact pending/dirty/error/saved
feedback and duplicate-submit protection. Page navigation offers save-and-go,
continue editing and explicit draft discard; browser unload protection remains.
Metadata and document writes still use successive page versions. If metadata saves
but the document fails, the draft and advanced version remain available for retry.
Conflicts require an explicit reload to replace the local draft. Page actions include
copy link, parent selection excluding descendants, recoverable branch trash and
restore. A trashed descendant directs the user to its trash-batch root.

Calendar backlinks and existing material attachment controls remain below the body;
removing a material reference preserves the material. No global search, automatic
save, page-page link schema, editor library, backend migration or new dependency was
introduced by this UI slice. Large libraries currently require all page summaries
for the tree/parent picker; lazy branch loading is a future performance improvement.

## Further Notion-style capabilities

This is a capability inventory, not authorization for the next slice. Detailed
requirements stay in [workspace requirements](../product/workspace.md), with
unresolved choices in [Q-06/Q-08](../product/open-questions.md).

| Capability | Status in Ukladen | Work needed next |
| --- | --- | --- |
| Page tree, independent pages, breadcrumbs, typed flat blocks, recoverable trash | Implemented | Current UI and existing notes API |
| Rich text, colors, nested/advanced blocks, quotes/code/toggles/columns | Requires a separate product decision | Q-08: versioned block/inline schema, validation, migration, rendering and editor behavior |
| Inline images and embeds | Requires a separate product decision | Block references to owned materials, media access and remote embedding policy; attachments already exist separately |
| Links/backlinks | Partially implemented | Calendar backlinks, material references and ordinary HTTP link blocks exist; typed page-page links/backlinks need relations API and persistence within the current architecture |
| Revision history | Partially implemented | Optimistic version checks exist, retained revisions do not; Q-06 must define retention and restore semantics before storage/API work |
| User databases and table/calendar views | Implemented | Existing independent database area with typed properties, saved queries and page-backed records |
| Additional database list/board views | Absent; fits current architecture | Extend saved layout contracts and UI over existing records; no record copies |
| Formulas and rollups | Requires a separate product decision | Owner-deferred; expression/dependency rules, query cost and relation contracts |
| Templates | Absent; fits current architecture | Explicit copy semantics, fresh block IDs and template storage/API; no implicit academic grouping |
| Import/export | Absent; fits current architecture | Explicit formats, compatibility/size rules and loss reporting; derived Markdown is not an export subsystem |
| Comments | Requires a separate product decision | Personal annotation versus shared discussion, anchors, authorship and lifecycle |
| Simultaneous editing and shared spaces | Requires a separate product/architecture decision | Owner-deferred; collaborator identity, synchronization, conflict protocol and ownership changes |
| Sharing/permissions and publishing | Requires a separate product/architecture decision | Owner-deferred; audience, revocation, public data exposure and access enforcement; copied links stay private |
| Global search | Partially implemented | Existing server full-text search over owned pages/materials in the search area; broader task/property coverage needs an explicit slice |
| AI | Partially implemented | Local chat, reads, retrieval and confirmed proposals exist but remain default-disabled/unactivated; real-provider checks and activation need separate authorization |
| Integrations | Partially implemented | Public IIS schedule/context exists; other calendar providers and private IIS need separate requested scopes and verified contracts |

UI verification on 2026-10-28: frontend lint, typecheck, production build, all 151
mocked-API Chromium tests, Compose validation and changed-document file links passed.
Light/dark desktop/tablet/mobile screenshots were inspected. The older backend
verification above remains separate; no live backend or provider request was used.
