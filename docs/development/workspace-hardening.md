# Personal workspace hardening

Implemented locally on 2026-11-22. Deployment requires migrations 0044 and 0045;
working containers and production data have not been migrated by this change.
Sharing and simultaneous editing are explicitly outside the requested scope.

## Recoverable AI answers

Assistant messages can retain up to 64 KiB and carry `incomplete=true`. Failed runs
record a bounded terminal reason, distinguishing output/context/step limits from
timeouts and provider errors. Visible partial output is saved for failed foreground
chat runs, reloaded through history and labelled in the transcript. The owner may
explicitly continue it with a fresh submission; recovery does not replay writes or
silently restart complete-source analysis. Stopping a run remains a cancellation;
this change does not guarantee persistence of text from a force-killed process.

The provider output default is 4096 tokens, configurable up to 8192. Explicit
catalog limits still win. Existing deployed images retain their previous default
until rebuilt. Storage bounds, provider token limits and tool argument limits are
different constraints; tool arguments and user messages retain their previous
16 KiB boundary. Model calls are bounded at eight per foreground run, with the
existing eight-tool and 60-second limits. The request middleware keeps complete
recent turns within a 20 KiB history budget, including paired tool messages. It
never splits a tool exchange or summarizes/deletes stored chat history. The current
turn is preserved; an oversized current request gets a context-limit reason.

A failed provider call closes unpaired checkpoint tool calls with safe errors and
finalizes the failed turn, so subsequent questions can run. Pending HITL interrupts
are preserved. Exact-digest owner approval remains mandatory for modifications.

## Writing and history

The editor autosaves 1.5 seconds after typing stops, retains optimistic versions,
serializes overlapping saves and preserves new typing during a request. Errors
pause automatic retries until an explicit save/reload. Navigation guards and manual
save remain. A browser crash before the debounce or an offline request can still
lose unsaved text; no local private-content cache or offline editor was introduced.

Each successful page creation/change retains an owner-scoped immutable snapshot.
The latest 50 snapshots per page are retained. Migration 0045 seeds existing current
pages; it cannot recreate earlier history. Frequent autosaves can use those 50 slots
quickly. Revision lists contain metadata only; a selected body is fetched separately.

- `GET /api/v1/notes/pages/{id}/revisions?limit=50&offset=0`
- `GET /api/v1/notes/pages/{id}/revisions/{version}`
- `POST /api/v1/notes/pages/{id}/revisions/{version}/restore` with `expected_version`

Restore requires the active owner, CSRF and current version. It restores title/body,
keeps the current hierarchy and creates a new revision. It never rewinds the version
number or erases the version being replaced. Downgrade refuses to destroy retained
history or new partial-answer data.

Markdown text blocks now offer bold/italic/code controls and a formatted preview.
Quote, code, table and nested-list starters use the existing Markdown representation;
these starters retain Markdown storage. Native recursive toggle sections and
owned database-view reference blocks were added on 2026-11-23, within the existing
versioned envelope; see [notes contracts](notes.md) and
[ADR 0011](../adr/0011-add-nested-blocks-and-owned-view-embeds.md).
History renders Markdown safely and shows static database references, not a record
snapshot. AI approval previews include descendant content and formatted Markdown.
Raw HTML and remote images are not executed/loaded by this renderer.

## AI in the workspace

“Discuss with AI” on a saved page and selected-text discussion prepare the floating
chat with explicit page scope. Existing AI drafts require an explicit replacement.
No provider request is made until Send. The composer can also select the current
page/calendar context. Calendar scope authorizes the existing calendar tools; it
does not narrow the backend to one event by itself.

Assistant answers, including partial ones, can be explicitly saved as a new owned
page, with a reviewed title and the original Markdown content. The page library is
invalidated after creation.

`page_update` accepts either a full document or up to 32 `block_edits`, each containing
`block_id`, `before`, `after`. Each block is edited at most once; the exact `before`
fragment must occur exactly once. Missing/ambiguous text or stale versions reject
the proposal. Unchanged text and blocks are preserved. The same preview, digest,
owner approval, ordinary note services and revision history apply to point edits.
List-item point edits are not included; full validated document updates remain available.

The material reader and AI source viewer distinguish extraction from semantic
index readiness. Readiness is metadata, not a paid model call. The explanatory UI
separates retrieving fragments from reading complete sources. Index failures can be
retried explicitly; an unavailable status is not presented as ready.

## Verification

- Native PostgreSQL/Redis: 51 note/revision/chat HTTP tests passed.
- Native PostgreSQL/Redis: 61 action, agent and tool-selection tests passed.
- Existing frontend note/AI/calendar suites: 110 browser tests passed.
- Material reader suite: three browser tests passed at desktop/mobile widths.
- CLI browser scenarios: autosave, Markdown, history restore, saving a partial answer
  explicit continuation and selected-page source scope checked against synthetic owned fixtures.
- Python Ruff and Pyright, frontend ESLint/typecheck and production build passed.
- Production npm audit after upgrading Next/eslint-config-next to 16.4.6: zero
  production vulnerabilities at verification time.
- Full database/object restore drill passed on two disposable Docker projects;
  see [backup guide](workspace-backups.md).

No paid provider requests were made for these checks. These checks do not establish
provider reliability or prove every end-to-end production worker configuration.
Remaining expansion is tracked in [the implementation checklist](product-hardening-plan.md).

## Nested blocks and embedded views — 2026-11-23

The native slice adds bounded recursive toggle sections and owner-validated saved
view references. Deleting a view preserves records and leaves a readable unavailable
reference; existing broken references do not block unrelated page edits. AI point
edits resolve descendant UUIDs, preserve siblings and retain exact owner approval.
Tool descriptions are selected per task: the calendar-only description measured
585 UTF-8 bytes versus the previous shared 1908 bytes (not token counts).

Verification: 104 pure backend tests and 48 PostgreSQL/Redis-backed document,
AI-source and action tests passed. Backend Ruff/Pyright, frontend lint/typecheck,
and 62 existing content browser tests passed. A separate CLI browser scenario
verified nested autosave, collapse/reopen, owned table embedding and mobile library
navigation at 390px without horizontal overflow. No running-stack migration,
provider quota request or deployment was performed.

## Final local verification — 2026-11-23

The complete 2170-case backend collection passed across partitioned runs after
repairing stale test assumptions about tool discovery/model budgets and ensuring
a refused downgrade rolls back its outer transaction. Migration roundtrip and
metadata comparisons include page revisions and import receipts. Three initially
skipped cases were rerun successfully on disposable SeaweedFS/PostgreSQL/Redis:
file upload/download, avatar replacement and S3 → Redis → registered material task
→ owned search. The temporary resources contain only synthetic data.

All 356 existing frontend tests passed. Separate CLI scenarios verified nested
autosave/reopen, saved-view embedding, a single mobile library toolbar, JSON
download/import confirmation and no child insertion beyond depth 8. Production
build, frontend lint/typecheck, backend Ruff/Pyright and changed-document links
passed. Existing LangChain/Python 3.14 compatibility/deprecation warnings remain.

One live streaming probe through the configured OpenRouter adapter returned a
valid `propose_actions` event batch: 1566 input tokens and 137 output tokens,
configured output ceiling 4096. No tool was executed and no user data was changed.
Actual monetary cost was not returned in the adapter metadata. This provider-only
check does not substitute for deployment and a production Cloudflare smoke check.

Portable [page/database transfer](workspace-transfer.md) complements the separate
full [PostgreSQL/object-store backup](workspace-backups.md). Sharing remains deferred.
