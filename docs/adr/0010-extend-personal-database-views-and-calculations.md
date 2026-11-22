# ADR 0010: Extend personal database views and bounded calculations

Date: 2026-11-23.
Status: accepted direction for the owner-requested personal-workspace expansion;
implementation status is tracked in the hardening checklist.

## Context

The owner requested the improvements from the product audit, and explicitly chose
personal workspaces without sharing or simultaneous editing. Earlier decisions
in ADR 0007 deferred formulas and views beyond table/calendar. This request opens
that personal-workspace scope; it does not authorize collaboration or replace
existing page-backed records with a different persistence model.

## Decision

- Keep page-backed records, owner-scoped services and optimistic/schema versions.
- Save list and board layouts over existing records. Grouping references an active
  select/checkbox property by stable UUID. A board requires a grouping property.
  Missing/trashed grouping inputs require explicit repair. Deleting a view never
  deletes records or pages. Pagination and group counts must be explicit in the UI.
- Add explicit, one-way relations to records in another owned database. Relation
  targets are authorized through workspace application services; linking never
  copies page content, edits a target or creates an implicit reciprocal relation.
- Derived formulas and rollups are read-only property values, not authored copies.
  Definitions are versioned with the database schema. Ordinary record writes cannot
  supply computed values. No arbitrary Python, SQL, network or plugin execution.
- The initial formula language is bounded arithmetic with numeric literals and
  stable property references. Reject unbounded syntax, powers, attribute access,
  comprehensions and arbitrary function calls. Missing/invalid inputs produce an
  explicit calculation error, never an invented zero.
- Initial rollups aggregate explicitly related owned records. Bound reference counts
  and read work; preserve ownership, database/page trash rules and source identity.
  Missing inputs remain visible as errors instead of silently dropping facts.
- Avoid recursive formula/rollup dependency graphs in the initial implementation.
  Further expression types, automation and synchronization need their own concrete scope.
- Schema changes require preserving Alembic migrations. Downgrade must refuse to
  discard new authored definitions/relations/views.

## Consequences

Personal organization gains additional views and calculations without collaboration
infrastructure or changes to official calendar facts. Derived data changes when its
source changes, but calculation never performs writes to source records. API and UI
must distinguish editable values from derived output and explain bounded pagination.
