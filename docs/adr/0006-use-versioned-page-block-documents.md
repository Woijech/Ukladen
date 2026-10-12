# ADR 0006: Use Versioned Page Block Documents

Date: 2026-10-12.
Status: accepted and implemented for the owner-requested notes block slice,
including domain rules, JSONB migration and versioned HTTP operations. Backend only.

## Context

Independent pages, hierarchy, recoverable trash and page/calendar links already
exist. The owner requested the next backend slice: text, headings, lists, checkboxes
and links with stable block IDs, ordered editing and version-safe saves. Existing
Markdown pages must survive the transition. UI and collaboration are out of scope.

## Decision

- `notes` owns a single authoritative block document per page, independent of events.
- The document contains `schema_version: 1` and an ordered `blocks` array.
- Each block has a UUID unique within that document. Clients keep IDs when editing
  or reordering; new blocks get new UUIDs. Missing blocks in a replacement are deleted.
- Block types are `text`, `heading`, `list`, `checkbox` and `link`, with allowlisted
  fields and strict types. Lists are flat, bulleted or numbered; headings use levels
  1–6; links accept absolute HTTP/HTTPS URLs without credentials or control characters.
- Text supports `plain` and `markdown` formats. Existing Markdown is wrapped unchanged
  in one Markdown text block, without parsing or guessing its original structure.
- Persist the versioned document in JSONB through Alembic, replacing the text column.
  IDs, ownership, parents, timestamps, trash and calendar links remain unchanged.
- Return a derived Markdown projection through existing page `content` reads. Allow
  legacy text writes only for empty documents or a single Markdown text block, and
  keep that block's ID. Structured documents reject legacy body overwrites with 409.
- Expose whole-document read/replace with the page's `expected_version`. Creation,
  editing, removal and reordering are one atomic document save. Do not add a second
  document version, per-block storage tables or granular operation protocols yet.
- Bound documents to 1000 blocks, 1000 items per list, 100000 aggregate text/URL
  characters and 1 MiB of normalized UTF-8 JSON. Reject NUL and invalid Unicode.
- Refuse a storage downgrade while structured documents, custom block IDs or empty
  text blocks exist, rather than flattening blocks or losing their IDs. Empty
  documents and nonempty wrappers with the page UUID can downgrade losslessly.
- Use standard-library domain logic and the existing Pydantic/SQLAlchemy stack;
  no editor library or new dependency is needed for the backend contract.

## Consequences

The document schema is independent of a future editor. Existing Markdown remains
usable, while block clients work with typed structure and stable IDs. JSONB validation
has two layers: database envelope/size constraints and full application/domain rules.
The Markdown projection is derived and is never independently persisted or edited
on a structured page. Concurrent writers must reload after a version conflict.

Nested blocks, rich inline marks, embeds, files/material references, revision history,
export APIs, collaborative editing and user databases remain future requested slices.
A Markdown projection is not the planned export subsystem or HTML sanitization policy.

References: [notes](../development/notes.md),
[workspace architecture](../architecture/workspace.md),
[decisions](../product/open-questions.md).
