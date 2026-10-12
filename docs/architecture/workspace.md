# Workspace Backend Architecture

Updated: 2026-10-12.
Status: pages, hierarchy, branch trash and page/calendar links are implemented, backend only;
see [notes contracts](../development/notes.md) and [relations](../development/relations.md). Other capabilities remain a target design under
[ADR 0004](../adr/0004-keep-workspace-organization-optional.md), with current APIs documented separately. The owner confirmed pages/blocks/databases and mandatory table/calendar views,
with personal ownership. Formulas and collaboration are deferred; remaining details
are recorded as open decisions.

## 1. Preserve the existing system

Keep the modular monolith, authentication, profiles, official schedule storage and
personal calendar API. New workspace features extend those modules through application
services/ports; they do not replace everything with a generic JSON entity table.

The current calendar stores typed personal events and per-user official overrides.
It has no mandatory `subject_id` or page parent. Existing HTTP routes must retain
their documented semantics while new page/view contracts are introduced.

## 2. Ownership by module

| Boundary | Owns | Does not own |
| --- | --- | --- |
| `notes` | Pages, content documents/blocks, page hierarchy, content versions and trash | Event times, attendance, database property schemas |
| `workspace` (planned new boundary) | Collections/membership, tags/assignments, user databases/property values and saved view definitions | Page body, shared official facts, planning rules |
| `relations` | Optional links between authorized typed objects and backlink queries | Page containment, database property storage, task dependencies |
| `calendar` | Personal events, official overrides, resolved events, availability/conflicts, calendar composition | Source imports, page content, custom property definitions |
| `schedule` | Shared official occurrences, normalization, synchronization, provenance | Personal grouping or content |
| `tasks` | Typed work state, deadlines, dependencies and task-block lifecycle | Arbitrary database records or page body |
| `subjects` | Optional academic organization, only if explicitly implemented | Mandatory workspace hierarchy |
| `materials` | File/link metadata, access and processing state | Page text or raw binaries in PostgreSQL |
| `search` | Permission-filtered indexes and retrieval | Canonical content ownership |
| `ai` | Conversations, authorized tools, proposals and orchestration | Independent copies of business rules |

`workspace` is a logical boundary until its slice is requested. Do not generate
empty packages, repositories or DTOs now. Existing packages do not need renaming.

## 3. Planned data contracts

These names describe responsibilities, not final table layouts. Every concrete
slice must specify SQL constraints, Alembic changes and transport DTOs before coding.

### Pages and documents

- `Page`: UUID, owner, title, optional parent, version, timestamps and trash state.
- `PageDocument`: content format/version and validated content; independent of any
  subject or calendar interval.
- `Block`: stable identity, type, validated payload and order/containment in the
  owning document, introduced only with the block editing slice.

A first text-only document can use Markdown/text with an explicit format version.
Do not claim block support or pick an editor's opaque JSON before Q-08 is resolved.
When blocks arrive, schema-versioned JSONB is acceptable for document content;
ownership, parents, reference integrity and queryable fields remain relational.
Choose one authoritative content representation per document. Do not keep independently
editable Markdown and block JSON as competing sources of truth.

Root pages are normal. Page-parent cycles and cross-owner moves are rejected by the
application and appropriate database constraints. Document updates require optimistic
version checks. Concurrent moves must not produce cycles; serialize the relevant
owner/tree mutations or use an equivalent demonstrated database guarantee.

### Organization and databases

- `Collection` and `CollectionMembership`: user-owned named sets and typed references.
- `Tag` and `TagAssignment`: personal labels; an upstream subject string is not a tag ID.
- `Database`: user-owned schema container.
- `PropertyDefinition`: stable ID, name, supported type, configuration and schema version.
- `DatabaseRecord`: database membership referencing a content page, with its own identity.
- `PropertyValue`: value validated against that definition in that database.
- `SavedView`: source, layout, allowed filters, sorting and optional date binding.

One content page can be referenced without copying its body. If a page participates
in multiple databases, values are scoped to each database record; names do not make
different property definitions equivalent. This is a proposed behavior to confirm
under Q-12 before implementing database membership.

Implement table and calendar view query contracts for the same records; other layouts
are optional. Formulas are explicitly deferred by the owner.

Start with a bounded type set: text, number, checkbox, select/multi-select, URL and
date/date-range. Relations require endpoint validation and may be a later property
type. Formula/rollup engines and arbitrary user-executable code are out of the first
database slice. Type conversions must be explicit, validated and reject data loss.

Keep stable property IDs when names change. Index the fields actually queried;
do not assume arbitrary JSONB properties are efficiently searchable without design.
Use a versioned, allowlisted filter expression rather than accepting raw SQL.

### Typed links

An `EntityRelation` identifies its owner, endpoint types/IDs and supported link kind.
Creating a link verifies both endpoints through their application interfaces. A
duplicate link must not create duplicate backlinks. Unlinking never deletes content.

Prefer typed association tables with foreign keys where practical. If a polymorphic
reference is selected, document its integrity/cleanup strategy: type-plus-UUID alone
is not an enforced foreign key. The same applies to mixed collection memberships.
Avoid building a universal entity registry before a real cross-type slice needs it.

Task dependency edges remain in `tasks`, where cycle rules belong. Page hierarchy
remains in `notes`; these are not generic links with special meaning inferred later.

## 4. Calendar views and date projection

Existing `GET /api/v1/calendar/events` returns official/personal events with their
current source and write identities. Do not relabel a page-date projection as a
personal event to fit that DTO. Introduce an explicit additive projection/composition
contract when the view slice is implemented; document compatibility before changing
the existing endpoint.

Planned composition:

```text
Saved view definition
  + authorized resolved calendar events
  + authorized dated database records / task deadlines
  -> discriminated display entries with source identity and edit target
```

`calendar` composes through `workspace`/`tasks` application query interfaces. It never
reads another module's ORM tables directly. Workspace date queries apply ownership
and property-schema validation before returning bounded records.

A projected entry identifies record and bound property, not only page title. Moving
it updates that property through `workspace`; moving an event calls `calendar`.
Date-only values are calendar dates, timed values use explicit offsets/IANA timezone
rules, and intervals have positive duration. All-day/recurrence representation must
be decided under Q-05 before finalizing DTOs.

Filtering is presentation only. Availability uses the full authorized busy set, not
the currently selected visual view. A task deadline or record date defaults to
nonblocking; actual work reservation uses an explicit typed calendar/task block.

## 5. Mutation, lifecycle and reference rules

Use the current opaque session and Origin/CSRF protection. Owner identity comes from
the session, never an arbitrary `user_id` in JSON. Recheck canonical active-user state
on writes; use consistent lock order and caller-owned transactions.

- Page/content/schema edits carry expected versions; stale writes fail without overwriting.
- Reads and lists are owner-filtered, bounded and exclude trashed content by default.
- Distinguish unlink, remove membership, trash and permanent purge operations.
- Deleting a view/collection must not cascade into its referenced pages/events.
- Exact nested trash/restore semantics must be defined before hierarchical deletion.
- Index cleanup and blob cleanup follow committed state and support retries.
- Unknown/foreign endpoints produce safe errors without leaking private titles/content.

User-owned links to official events survive source withdrawal as historical links.
Group changes do not delete user content. Use stored caller-owned references for
historical resolution; never expose unrestricted event-ID lookups as a shortcut.
Current source identity limitations remain until verified matching improves them.

## 6. Application operations and transport design

The first page slice should expose services for `create_page`, `list_pages`,
`get_page`, `update_page`, `trash_page` and `restore_page`. Hierarchy adds `move_page`;
blocks add validated document operations. No operation requires a subject.

Implemented page HTTP routes (full behavior in [notes](../development/notes.md)):

| Operation | Proposed route |
| --- | --- |
| List/create | `GET /api/v1/notes/pages`, `POST /api/v1/notes/pages` |
| Detail/edit | `GET /api/v1/notes/pages/{page_id}`, `PATCH /api/v1/notes/pages/{page_id}` |
| Recoverable deletion | `POST /api/v1/notes/pages/{page_id}/trash` |
| Restore | `POST /api/v1/notes/pages/{page_id}/restore` |

Current notes contracts specify title/content limits, pagination, expected-version
semantics, error codes and explicit omitted/null behavior. Transport schemas and
OpenAPI must describe the implemented slice, not every future feature.

Organization services later add collection/tag membership, schema/record CRUD and
view queries. Relation services already provide page/calendar link/unlink and backlink queries. These must
remain normal application operations reusable by HTTP and AI.

## 7. Verification requirements

Each slice needs tests for meaningful rules: ownership/CSRF, versions, rollback,
preservation on unlink/view deletion, hierarchy cycles/concurrent moves where relevant,
typed property validation and permission-filtered date projection.

Native PostgreSQL tests verify migrations, foreign keys, conflict behavior and
transactional integrity. Keep the existing calendar/schedule tests passing.
No test calls IIS or an LLM by default. Match the roadmap's acceptance cases;
do not generate tests for empty scaffolding.

References: [requirements](../product/workspace.md),
[implementation roadmap](../development/implementation-roadmap.md),
[current calendar contract](../development/calendar.md).
