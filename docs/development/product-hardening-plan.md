# Product hardening and workspace expansion

Requested on 2026-11-22 after the repository/product audit. Preserve A1, owner-scoped
access, exact AI confirmations and official schedule facts. Each checkbox represents
implemented, verified behavior; planned work is not a shipped feature.

## Reliability

- [x] Persist bounded partial AI answers and explain terminal reasons.
- [x] Continue after truncation/failure without replaying writes or losing text.
- [x] Align model output, message storage and transport budgets.
- [x] Bound conversation context and reserve enough steps for complex requests.
- [x] Fix assistant overlap and the ambiguous event-deletion test.
- [x] Update vulnerable frontend dependencies and verify the production build.

## Writing and recovery

- [x] Autosave versioned page changes without overwriting concurrent edits.
- [x] Persist and restore owned page revisions.
- [x] Add inline formatting and Markdown quote/code/table/nested-list starters.
- [x] Add native recursive rich blocks beyond Markdown.
- [x] Provide workspace export/import with explicit validation and confirmation.
- [x] Provide complete backup/restore tooling for PostgreSQL and object storage.

## Connected workspaces

- [x] Add database relations, rollups and bounded formulas.
- [x] Add grouping and additional database views.
- [x] Embed saved database views in pages.
- [x] Give AI explicit context for the open page/event and selected text.
- [x] Add safe point edits and saving AI output to a page.
- [x] Clarify extraction/indexing/full-document states in the UI.

## Design and validation

- [x] Consolidate mobile note toolbars and remove duplicated assistant labels.
- [x] Give failure states concrete recovery actions.
- [x] Exercise browser flows and native API/worker/retrieval paths with synthetic owned data.
- [x] Update capabilities documentation and run applicable checks.

The owner explicitly selected personal workspaces first. Sharing and simultaneous
editing remain outside this work, as previously deferred in the architecture.

Completed local verification on 2026-11-23: all 2170 backend cases passed across
partitioned runs. Three initially skipped storage scenarios were then run against
disposable SeaweedFS/PostgreSQL/Redis and passed. All 356 existing frontend cases
passed; additional CLI scenarios covered recursive editing, embedded views,
transfer confirmation and the depth limit. Browser tests use intercepted API
fixtures; native HTTP/task/storage tests use isolated real infrastructure.
One real configured-provider streaming probe validated a synthetic proposal without
executing tools (1566 input / 137 output tokens; actual cost not reported).
This is local delivery, not deployment or a production Cloudflare smoke check.
