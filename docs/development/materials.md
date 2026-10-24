# Materials and Basic Search

Updated: 2026-10-22.
Status: P-08 backend implemented. Materials and full-text search UI are described
in the [frontend guide](../architecture/frontend.md). OCR, legacy DOC/PPT conversion,
remote-page fetching, embeddings, semantic search and RAG are not implemented.

## Scope and limits

Materials are independent owner-scoped files or HTTP/HTTPS bookmarks. Pages may
reference them explicitly through `relations`; no subject, database or calendar
event is required. URLs are validated and stored, never downloaded by the server.

| Limit | Implemented contract |
| --- | --- |
| File size | 25 MiB = 26,214,400 bytes, nonempty |
| Retained file storage per user | 1 GiB = 1,073,741,824 bytes |
| Retained materials per user | 10,000, including bookmarks, incomplete uploads and trash |
| Filename/title | 1–200 characters; filenames cannot contain paths or control characters |
| Bookmark URL | At most 2,048 characters; HTTP/HTTPS without embedded credentials |
| Extracted text | At most 2 MiB UTF-8 per document, also subject to PostgreSQL FTS limits |
| Trash retention | Restore before 30 days; periodic permanent cleanup after that |
| Incomplete upload | Finalize within one hour; periodic cleanup afterwards |

The owner confirmed the file/storage limits and exclusion of OCR. Retention,
parser budgets and count limits are documented implementation defaults, not a
promise of unlimited documents or production throughput. The byte quota covers
material originals; avatars, extracted text, indexes, backups and database overhead
are separate. Reservations, failed files and trash continue consuming quota until
permanent cleanup succeeds. Bookmarks consume no file bytes.

## Storage and ownership

`materials` stores metadata, ownership, optimistic versions, processing state and
leases in PostgreSQL. Original bytes use the existing private S3 bucket under
server-generated `materials/{owner UUID}/{material UUID}` keys. These keys and
storage credentials are not returned by the API. Binary content is never stored
in PostgreSQL. Existing avatar APIs and their separate keys remain compatible.

Upload reservations are committed before any S3 write. A separate object ledger
survives hard deletion of a user/material so maintenance can remove orphan objects.
If S3 succeeds but the metadata transaction fails, the reservation still tracks
the possible object. Retry can replace that unfinalized object; otherwise expiry
cleanup removes it. Successful finalization makes the binary immutable.

Writes take the shared active-user lock, preventing concurrent quota overbooking
and serializing lifecycle/version changes. Foreign/missing UUIDs return 404.
Disabled users cannot access or process materials. Download requires an active,
untrashed, finalized file; extraction failure does not remove the original.

## HTTP contracts

All routes require an active browser session and return `Cache-Control: no-store`.
Writes require the existing CSRF cookie/header and allowed Origin. JSON DTOs reject
unknown fields. Prefix: `/api/v1/materials`.

| Method and path | Input / result |
| --- | --- |
| `POST /uploads` | `{filename, size_bytes, title?}` → 201 metadata in `uploading` state |
| `PUT /{id}/content` | Raw file body with its declared MIME type → metadata in `pending` state |
| `POST /links` | `{title, url}` → 201 bookmark metadata in `ready` state |
| `GET /storage` | `{used_bytes, material_count, limit_bytes, max_file_bytes}` |
| `GET ""` | `trashed=false`, `limit=100` (1–200), `offset=0` → `{items, limit, offset}` |
| `GET /{id}` | Metadata, including trash state |
| `GET /{id}/content` | Private attachment download; no inline rendering or public URL |
| `PATCH /{id}` | `{expected_version, title?, url?}`; URL edits only for bookmarks |
| `POST /{id}/trash` | `{expected_version}` → recoverable trash |
| `POST /{id}/restore` | `{expected_version}` → active material before retention expiry |
| `POST /{id}/retry` | `{expected_version}` → failed file returned to `pending` with attempt budget reset |

Metadata fields: `id`, `title`, `kind` (`file`/`link`), `filename`, `media_type`,
`size_bytes`, `url`, `status`, `version`, `error_code`, `created_at`, `updated_at`
and `trashed_at`. Background transitions also increment `version`; clients should
reload metadata after a version conflict. Explicit null patches are rejected.
List endpoints have no total-count promise.

Upload is two requests, not multipart or direct-to-S3. The body must exactly match
the reserved size. It is spooled to disk above 1 MiB and checked against the hard
25 MiB cap even without `Content-Length`. PDF/OOXML signatures are checked before
storage; complete parsing happens asynchronously. Failed/interrupted uploads retain
their reservation until retry or cleanup. There is no resumable/chunk upload API.

| Extension | Required upload Content-Type |
| --- | --- |
| `.pdf` | `application/pdf` |
| `.docx` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |
| `.pptx` | `application/vnd.openxmlformats-officedocument.presentationml.presentation` |
| `.txt` | `text/plain` |
| `.md` | `text/markdown` |

A Content-Type charset suffix is allowed. Unsupported extensions/types, size
mismatch and malformed input return 422; streamed bodies over the limit return
413. Declared sizes outside the upload DTO range return 422 before reservation.
Quota/count/version/state conflicts return 409, inaccessible objects 404, and
temporary storage failures 503. Downloads use `application/octet-stream`, an
encoded attachment filename and `X-Content-Type-Options: nosniff`.

## Optional page attachments

Prefix: `/api/v1/relations`.

| Method and path | Behavior |
| --- | --- |
| `PUT /pages/{page_id}/materials/{material_id}` | Add an owner-validated link; duplicates are idempotent |
| `DELETE /pages/{page_id}/materials/{material_id}` | Unlink only |
| `GET /pages/{page_id}/materials` | Forward metadata list |
| `GET /materials/{material_id}/pages` | Backlink page list |

Lists use `limit=100` (1–200) and `offset=0`. Both endpoints must be owned by the
caller; new associations require active objects. Trash preserves existing links
and metadata. Deleting a link or page does not delete material bytes; permanent
material cleanup removes its associations without deleting pages. Attachments are
relations, not embedded block payloads or automatic membership propagation.

## Extraction and failure recovery

State flow: `uploading → pending → processing → ready/failed`. Transient storage
errors return work to `pending` while its three-attempt budget remains. Parser
errors are terminal until explicit retry. Empty/scanned PDFs become `ready` with
`no_extractable_text`: their title is searchable and original downloadable.

PDF extraction uses the locked `pypdf` dependency. DOCX/PPTX use standard-library
ZIP/XML parsing. Text/Markdown require UTF-8. DOCX indexes main-body paragraphs and
tables; PPTX indexes slide text/tables in presentation order. Images, handwritten
content, PDF scans, Office headers/footnotes/speaker notes and external resources
are not OCRed or fetched. Password-protected/encrypted documents are rejected.

Each parser runs in a child process without service credentials, with Linux limits
of 768 MiB address space, 40 CPU seconds and 60 seconds wall time. PDFs/slides are
bounded to 500 pages/slides. OOXML is bounded to 5,000 archive entries, 100 MiB
declared uncompressed data and 8 MiB per XML part; traversal, encrypted archives,
duplicate entries, macro content types and XML DTD/entities are rejected.
These are resource limits, not a complete malware sandbox. Originals are preserved.

`error_code` is a fixed category: `invalid_document`, `document_limit`,
`storage_unavailable`, `processing_timeout` or the informational
`no_extractable_text`. Parser text, filenames, URLs, object keys and raw exception
messages are not included in job diagnostics.

Claim/complete transactions use a two-minute fenced lease. File retrieval/parsing
occurs outside a database transaction; index publication and successful completion
commit together. Duplicate messages and late results cannot overwrite a newer
attempt. Expired leases are recovered; three failed/crashed attempts stop automatic
processing. Trash during extraction suppresses index publication. Search always
rechecks canonical ownership/trash/status, even if derived text exists.

Beat dispatches `materials.dispatch` every 30 seconds on the normal queue. It also
cleans expired uploads/trash and orphan objects. Batches select at most 20 processing
items, 50 expired materials and 50 orphan objects. `materials.process` uses the
`materials` queue and the Compose `material-worker` (concurrency 1, prefetch 1).
The normal worker retains email/schedule/reminder jobs. PostgreSQL is authoritative;
after a broker restart, later scans redispatch pending/expired work. Cleanup deletes
S3 content before metadata/ledger removal and quota release; failure leaves durable
retry state. Run one Beat instance and both workers.

## Basic search

[AI-03](ai-03.md) adds an internal material-owned bounded extracted-text read interface
over the existing derived text, with current owner/readiness/trash checks and Unicode
character positions. No new file download or bookmark-fetch endpoint is introduced.

`GET /api/v1/search?q=...` returns `{items, limit, offset}`. Each hit includes
`source` (`page`/`material`), `id`, `title`, plain-text `snippet` (up to 600 characters),
`score`, `version` and `kind` (`file`/`link`, null for pages).

Query limits: 1–200 trimmed characters, at most 30 whitespace-separated words,
`limit=20` (1–50), `offset=0` (0–1000). Optional filters: `source=page|material`,
`kind=file|link`, `extension=pdf|docx|pptx|txt|md`. Contradictory combinations return
422. No user-supplied SQL, regular expressions or advanced tsquery syntax is used.

Search combines PostgreSQL `simple`, `russian` and `english` full-text configurations,
with title weighting above body text. It returns lexical matches, not semantic
answers or arbitrary substring matches. Page bodies come from canonical typed block
text; metadata UUIDs/type names and link URLs are not indexed. GIN expressions
update transactionally on page edits. File text is a derived search-owned table;
material titles remain searchable before processing and after extraction failure.
Bookmark search covers titles, not fetched web pages. Trashed objects and other
owners' content are excluded in SQL. Both sources share one repeatable-read snapshot.
Ties are ordered by source and UUID for repeatable pagination on unchanged data.

## Upgrade and verification

No new provider/account/API key is needed. Reuse `DATABASE_URL`, `REDIS_URL` and the
existing S3 settings. Apply migrations `0019_materials` and `0020_basic_search`, rebuild
the backend image and recreate API, normal worker, `material-worker` and Beat using
the appropriate local/home Compose profile. See [local development](local-development.md)
and [home deployment](../deployment/home-server.md). This task does not deploy them.

Downgrading `0019_materials` refuses retained material/ledger data rather than
silently discarding originals. `0020_basic_search` removes derived search structures;
after rebuilding that index, previously processed files need explicit reindexing
(no public reindex API is included). Back up PostgreSQL and S3 together before
changing an existing deployment. A user quota does not reserve physical disk space.

Tests use disposable PostgreSQL schemas, Redis prefixes/queues and private S3 keys.
Set `AUTH_TEST_DATABASE_URL`, `AUTH_TEST_REDIS_URL` and the existing
`AVATAR_TEST_S3_ENDPOINT`, `AVATAR_TEST_S3_ACCESS_KEY`, `AVATAR_TEST_S3_SECRET_KEY`,
`AVATAR_TEST_S3_BUCKET` variables to include native integration tests. GitHub Actions
now provisions disposable SeaweedFS for these tests. Local evidence includes native
S3 round trips and Redis message consumption through the registered Celery task;
it does not constitute a live worker-daemon load test. See the dated P-08 verification
record below for executed checks.

## Verification (2026-10-16)

Executed locally: Ruff lint, Ruff format check, Pyright, the complete backend pytest
suite against disposable PostgreSQL 18, Redis and SeaweedFS (**1450 passed, no skips**),
base `docker compose config --quiet`, and the merged home Compose exposure/secrets/
proxy-trust check. Tests include native original upload/download, an actual Redis
message executed by the registered task, parser budgets, ownership/CSRF, concurrent
quota reservation, lease fencing/retries, index rollback and cleanup failure recovery.
Existing avatar and workspace/calendar/reminder tests passed in the same suite.

GitHub Actions, Docker image builds, a complete running Compose stack, frontend
checks and a live worker-daemon throughput test were not executed for P-08.
No deployment, push, real-user migration or production configuration change was made.
The quota is a product limit, not evidence that 1,000 active users fit this machine;
physical storage, backups and real workload measurements remain deployment planning.
