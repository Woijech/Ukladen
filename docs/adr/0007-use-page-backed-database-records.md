# ADR 0007: Use Page-Backed Database Records and Recoverable Schema Changes

Date: 2026-10-15.
Status: accepted implementation design for the owner-requested P-05 backend slice.
Property validation is implemented; persistence, HTTP and database views are not
implemented yet. Delivery status is maintained in [the database guide](../development/databases.md).

## Context

Pages, block documents, organization and saved event views exist. P-05 requires
user-defined schemas, page-backed records and table/calendar views over the same
records. The owner authorized implementation with incremental local commits and
delegated choosing the best membership/lifecycle model for this personal workspace.

## Decision

- `workspace` owns database metadata, property definitions, record values and saved
  database views. `notes` remains the sole owner of page titles, bodies and hierarchy.
- A page may participate in several databases. Each database has at most one
  record for a page, including trashed records. Its values belong to that record.
  Membership is explicit and never propagates through nesting, links or collections.
- Store database/property/record metadata relationally with owner-scoped composite
  foreign keys. Records reference existing pages or create a page atomically through
  `NoteService`. Do not copy page titles/bodies into records.
- Store property options and the bounded map of values in JSONB, validated against
  stable property and option UUIDs. This is a typed workspace schema, not a universal
  entity table. PostgreSQL enforces relational ownership and JSON envelope/size limits;
  application/domain rules enforce property types, options and values.
- Database metadata, properties, records and views have optimistic versions.
  Databases additionally expose a schema version. Property changes increment it;
  value writes require the current schema version as well as the record version.
  All writes share the existing canonical active-owner lock and caller transaction.
- Databases, properties and records use explicit trash/restore. Database trash
  changes only the database's lifecycle state; restoring it preserves each child's
  independent trash state. Property trash retains all record values. Record trash
  never trashes a page. Permanent purge is outside this slice.
- Schema conversions validate every retained record, including trash, before any
  changes are committed. Supported lossless conversions are text/URL and select/
  multi-select with compatible values. Unsupported populated conversions and removal
  of used options are conflicts. Converted records receive new versions atomically.
- Table/calendar views reference the same records. Store allowlisted, versioned
  filter/sort/column settings; validate referenced properties when saving and querying.
  Deleted/trashed filter or date properties require explicit repair, never broadening
  selection silently. Deleting a view removes only its settings.
- Calendar views bind explicitly to a date property. Date-only values remain dates;
  timed values require explicit offsets. Projected entries retain record/property
  write identities and are nonblocking. Moving a projection updates that property.
  Calendar composition uses application query ports and an additive display contract,
  preserving the existing event API and full busy-time truth.
- New schema migrations preserve existing pages/events. A downgrade refuses to drop
  populated database tables rather than silently deleting authored schemas/values.
- Keep the existing stack; no major dependencies, formula engine, collaboration,
  typed task state or UI are introduced.

## Consequences

The same page body can appear in several explicit organizations without duplication.
Record values, typed planning state and event time retain distinct ownership.
Recovery does not require inventing revision history or synchronizing copied documents.
Clients must refresh schema/record versions after conflicts. Historical property
values consume storage until a later explicit purge policy is implemented.

References: [requirements](../product/workspace.md), [decisions](../product/open-questions.md),
[workspace architecture](../architecture/workspace.md), [roadmap](../development/implementation-roadmap.md).
