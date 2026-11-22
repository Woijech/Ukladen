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
- [ ] Add native recursive rich blocks beyond Markdown.
- [ ] Provide workspace export/import with explicit validation and confirmation.
- [x] Provide complete backup/restore tooling for PostgreSQL and object storage.

## Connected workspaces

- [ ] Add database relations, rollups and bounded formulas.
- [ ] Add grouping and additional database views.
- [ ] Embed saved database views in pages.
- [x] Give AI explicit context for the open page/event and selected text.
- [x] Add safe point edits and saving AI output to a page.
- [x] Clarify extraction/indexing/full-document states in the UI.

## Design and validation

- [ ] Consolidate mobile note toolbars and remove duplicated assistant labels.
- [x] Give failure states concrete recovery actions.
- [ ] Exercise browser/API/worker/retrieval together with synthetic owned data.
- [ ] Update capabilities documentation and run applicable checks.

The owner explicitly selected personal workspaces first. Sharing and simultaneous
editing remain outside this work, as previously deferred in the architecture.
