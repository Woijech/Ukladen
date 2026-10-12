# ADR 0004: Keep Workspace Organization Optional

Date: 2026-10-12.
Status: accepted product direction from the repository owner; implementation not started.

## Context

The previous blueprint emphasized subject workspaces and scheduled `subjects`
before notes. This could imply mandatory academic grouping or automatic merging
of lectures and labs. The owner requires standalone notes, user-controlled calendar
organization, optional grouping and a broader Notion-like workspace with AI and IIS.

The existing calendar supports standalone personal events. Its official facts/override
separation is compatible with this direction and must be retained.

## Decision

- Pages and personal events are independent objects. Neither requires a subject.
- Nesting, relations, collections, tags and saved views express user choices.
- Equal subject labels never merge occurrences, link pages or propagate edits.
- `subjects` is optional, not a required workspace parent.
- Calendar presentation is separate from ownership and time-blocking semantics.
- Keep `notes` for page/content ownership. Add a `workspace` boundary for user
  organization and database/view schemas when that slice is implemented. It is
  planned; this ADR creates no empty package or database schema.
- Put standalone pages and optional organization before subject-specific features.
  Preserve the modular monolith and existing APIs.
- Authenticated IIS capabilities and full editor/database scope remain unresolved
  contracts where owner choices or upstream evidence are missing.

## Consequences

Architecture, product requirements and development order are aligned. Blocks,
databases, date projections and AI remain planned. Concrete API/SQL schemas belong
to implementation slices; the architecture does not replace typed entities with
an unvalidated universal JSON object table.

No runtime behavior, schema, frontend, credentials or calendar data changes in this task.

References: [workspace requirements](../product/workspace.md),
[workspace architecture](../architecture/workspace.md),
[open decisions](../product/open-questions.md).
