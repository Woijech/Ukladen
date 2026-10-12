# ADR 0004: Keep Workspace Organization Optional

Date: 2026-10-12.
Status: accepted product direction from the repository owner. Independent pages,
hierarchy, trash, calendar links and flat typed blocks are implemented; user
organization/databases/views remain planned.

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
- Pages, blocks and databases with table/calendar views are confirmed targets;
  exact schema/editor details remain open. Formulas and collaboration are deferred.
- Current IIS scope is public schedule/context; private student capabilities are
  deferred plans whose upstream contracts remain unverified.

## Consequences

Architecture, product requirements and development order are aligned. At decision
time, blocks, databases, date projections and AI were planned. Concrete API/SQL schemas belong
to implementation slices; the architecture does not replace typed entities with
an unvalidated universal JSON object table.

No runtime behavior, schema, frontend, credentials or calendar data changes in the
original documentation task. Subsequent implementation delivers standalone pages,
hierarchy, trash, page/calendar links and flat typed blocks; see
[notes](../development/notes.md), [relations](../development/relations.md) and
[ADR 0006](0006-use-versioned-page-block-documents.md) for current contracts.

## Owner scope clarification (2026-10-12)

The owner confirmed pages/blocks/user databases and mandatory table/calendar views,
deferred formulas, private IIS and collaboration, and requested AI help/recommendations,
confirmed execution and explicitly permitted automatic actions.
[ADR 0005](0005-support-scoped-ai-action-permissions.md) records the AI authorization change.

References: [workspace requirements](../product/workspace.md),
[workspace architecture](../architecture/workspace.md),
[open decisions](../product/open-questions.md).
