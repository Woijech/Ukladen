# ADR 0011: Add nested blocks and owned saved-view references

Date: 2026-11-23.
Status: accepted implementation design for the requested personal workspace;
delivery remains tracked in the hardening checklist.

## Decision

Extend the existing schema-version-1 block union additively with a `toggle` block
(label plus ordered children) and a `database_view` block (caption and explicit
owned database/view UUIDs). Keep stable block identities, one canonical document,
optimistic writes and page history. No second editable Markdown representation.

Validate at most 1000 blocks across the whole tree, eight levels of nesting, 20
embedded references, 100000 content characters and the existing 1 MiB envelope.
IDs are unique across all descendants. Domain parsing remains independent of
infrastructure. Plain Markdown projection includes nested content and reference
metadata; it does not copy database records into the page body.

Notes validates new embedded references through an application read port. Its
adapter checks current view/database ownership in the same transaction. Already
stored references may remain when a view is deleted or a database is trashed;
normal editing must still work and show an unavailable reference. Restoring owned
historical content preserves its references without inventing replacement targets.
The embed always reads data through the normal authenticated view APIs. It never
executes scripts, remote HTML or arbitrary URLs. Removing a block removes only the
reference; deleting a view never deletes page content or member records.

The frontend/backend update is coordinated: earlier clients do not implement the
new union members. A preserving migration refuses downgrade while live pages or
retained revisions contain either new type. Legacy Markdown writes remain limited
to empty/single-Markdown documents, preserving the existing anti-loss rule.

History displays embedded reference metadata, not a silently changing historical
snapshot of database rows. Editing a nested block preserves unrelated descendants.
AI point edits and source reads must use stable descendant IDs, and the existing
exact confirmation/source validation boundaries remain mandatory.
