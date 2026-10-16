# Product Decisions and Open Questions

Updated: 2026-10-16.
Status: decision register. Owner-confirmed scope is distinguished from open design
choices. Proposed defaults are not owner confirmation; resolve relevant unknowns
before implementing incompatible schemas, integrations or behavior.

## Confirmed direction

- Combine a freely organized workspace/calendar with AI and public IIS schedule integration.
- Standalone pages and events work without academic context; organization is optional.
- Lecture/lab grouping is user-controlled, never inferred from equal source labels.
- Preserve official facts, personal overrides and existing backend contracts.
- Technical documentation/code is English; initial product text may be Russian.
- The owner requested the backend pages/hierarchy/calendar-link slice with incremental local commits.
- The owner subsequently requested the backend block-document slice with local commits.
- The owner then requested the backend organization slice with local commits.
  Collections/tags and explicit page/personal/official membership are implemented;
  saved calendar views were subsequently requested and implemented. The owner then
  requested P-05 databases/table/calendar views with incremental commits and delegated
  membership/lifecycle choices. This backend slice is implemented under ADR 0007.
- The owner requested P-07 reminders/notifications with incremental local commits.
  Existing calendar targets and the durable in-app inbox are implemented; P-06 tasks
  and additional notification channels are separate future work.
- The owner requested P-08 materials/basic search with incremental local commits,
  a 25 MiB file limit, 1 GiB file storage per user and no OCR. Implement locally;
  deployment may be requested later. No deployment or external processing provider
  is required by this slice.

[ADR 0004](../adr/0004-keep-workspace-organization-optional.md) records organization.
[ADR 0005](../adr/0005-support-scoped-ai-action-permissions.md) records AI authorization.

## Owner-confirmed answers (2026-10-12)

| ID | Confirmed decision | Delivery consequence |
| --- | --- | --- |
| Q-01 | Pages, blocks and user-defined databases are required. Table and calendar views are mandatory. Formulas are not needed now. | Deliver incrementally; a text-only slice is an intermediate step, not the complete workspace. List/board views and rollups are not first-release requirements. |
| Q-02 | Current IIS scope is schedule and related public data. Grades and other deep student-account integration remain future plans and are not being implemented now. | Preserve verified public adapters/sync; do not add private account connection, credentials, grade imports or private API investigation to current slices. |
| Q-03 | Shared spaces and collaboration are not needed now; they are later work. | Use personal owner-scoped data. No collaborator-membership, access-role, sharing or simultaneous-editing subsystem in current scope. |
| Q-04 | AI must provide reading/help, recommendations, execution after confirmation and explicitly permitted automatic actions. | Implement reads/recommendations, confirmed writes, then scoped automatic execution. Automatic actions require a real owner permission; this feature decision does not grant unrestricted execution. |

These answers replace the previous provisional defaults for Q-01 through Q-04.
Runtime status is recorded in implementation guides; confirming scope alone does not implement it.
Exact AI permissions/provider policy remain open below, rather than reopening the
confirmed requirement for automatic actions.

## Remaining decisions

| ID | Question | Proposed default | What depends on it |
| --- | --- | --- | --- |
| Q-04a | Which actions may run automatically, on which objects, for how long and with what limits? Which AI provider, budget and content-sharing policy apply? | No automatic writes without an explicit scoped grant. Without a matching grant, preview and confirm. Provider-neutral adapters; no provider chosen. | Grant policy, revocation, execution records, costs and external content transfer |
| Q-05 | Beyond mandatory database calendar views, which calendar features are required first: all-day events, recurrence, multiple calendars or external providers? | Existing timed events plus date projections; dates/deadlines are nonblocking. Recurrence/all-day contracts are separate; no Google/Microsoft sync assumed. | Date DTOs, recurrence/exception model and availability |
| Q-06 | Which history, purge and export features should follow recoverable trash? | Implemented branch trash restores its batch root and preserves previously trashed children; see [notes](../development/notes.md). No purge/history/export yet. | Future cleanup, history and export |
| Q-07 | Are tasks typed planning objects, database records, or both with an explicit binding? | Typed tasks retain planning rules; ordinary records do not become tasks automatically. | Task API, date bindings and AI tools |
| Q-08 | Which rich inline formatting, nested blocks and editor should follow the initial block slice? | Text, headings, flat lists, checkboxes and links are implemented, backend only. [ADR 0006](../adr/0006-use-versioned-page-block-documents.md) records the versioned schema and preserving migration. Page/material relations are implemented separately; embedded attachment blocks, UI/editor and rich formatting remain later work. | Future editor, rendering and export |
| Q-09 | Should optional subjects use templates or a separately imported catalogue? | Defer; never merge by label or require subject IDs. | Subject module and explicit academic relations |
| Q-10 | How should upstream replacements be reconciled without stable IDs? | Preserve historical references and expose uncertain replacements; explicit relinking. | Import matching, overrides and notifications |
| Q-11 | What further content/query and operational limits are required? | Owner confirmed 25 MiB/file, 1 GiB retained file storage/user and no OCR for P-08. Other slice limits are in [materials/search contracts](../development/materials.md); no production throughput promise. | Later quota changes, indexing and production readiness |
| Q-12 | Resolved on 2026-10-15 under the owner's delegation to choose the best fit: a page may belong to several databases, with a shared body and separate record values. | Membership is explicit. Databases, properties and records use recoverable trash; their deletion preserves page content and retained values. No permanent purge is included. | Database membership constraints and lifecycle |

These details do not block the confirmed documentation direction. Clarify only those
needed by the requested implementation slice; do not repeatedly ask whether pages,
databases, personal ownership or automatic AI actions are wanted.

## Future-only IIS questions

Private capability priority, authentication/consent, grade/curriculum/assignment
contracts, credential retention and write-back are deferred. Investigate them only
when the owner explicitly requests that phase. No private API contract is established.
Owner intent cannot establish an endpoint or payload; future implementation still
requires evidence, sanitized fixtures and adapter contract tests.

## Recording later decisions

Record the answer, date and affected requirements here. Update architecture/ADR when
boundaries or authorization change, then affected roadmap/product sections. Keep
current implementation status separate from confirmed future scope.

## Next decisions by slice

P-03 calendar-view implementation (2026-10-15): bounded per-source collection/tag
filters, day/week/month preference, chronological sort direction and hidden-event
preference are implemented over existing timed events. Deleted filter references
require repair; they never silently broaden selection. These implementation choices
are documented in [the API contract](../development/calendar-views.md). They do not
resolve Q-05's future all-day/recurrence/provider scope or database decisions Q-07/12.

- Standalone pages: document first-slice content limits and recoverable trash behavior.
- Future rich blocks/history: Q-06 and Q-08; initial blocks and hierarchy are implemented.
- Databases/calendar projection: Q-05, Q-07 and Q-12; table/calendar views are required.
- AI execution: Q-04a, idempotency, versions and provider data policy.
- Private IIS: deferred; requires a new phase request and verified upstream contracts.

P-05 database implementation (2026-10-15): Q-12 is resolved under owner delegation.
Each database is bounded to 100 retained properties and 10000 retained records;
values and queries have explicit byte limits in [database contracts](../development/databases.md).
Calendar binding uses an active date-property UUID, date-only or offset-aware timed
values and nonblocking projection. Mixed display preserves the existing event API.
Personal all-day events, recurrence, typed task deadlines and scoped AI execution
remain later decisions; P-05 does not implement them.

P-07 implementation choices (2026-10-15): one-shot personal/official calendar targets,
0–43200 elapsed UTC minutes before start, strictly future create/edit, and one durable
notification per reminder UUID. Moved/skipped/withdrawn/inaccessible targets cancel
at delivery evaluation; physical event deletion removes its reminders. Broker recovery
rescans PostgreSQL and catches up only before event end. These are documented slice
contracts, not owner confirmation of future task, recurrence or external-channel policy.
See [reminders](../development/reminders.md).

P-08 implementation choices (2026-10-16): PDF text/DOCX/PPTX/TXT/MD extraction,
bookmarks without URL fetching, optional page relations, 30-day material trash,
one-hour incomplete-upload expiry and bounded lexical search. Reservations, failures
and trash count against the confirmed file quota until permanent cleanup. Retained
material count, parser/time/text limits and recovery behavior are implementation
defaults, documented in [materials/search](../development/materials.md). These do
not resolve future semantic retrieval, provider budgets, malware isolation or
production capacity. OCR is explicitly excluded by the owner.
