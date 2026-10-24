# Product Decisions and Open Questions

Updated: 2026-10-21.
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
- On 2026-10-17 the owner chose free Groq calls for development and requested
  interchangeable providers, local or free API embeddings, an editable scenario
  catalog, staged connection instructions and usage analytics. The resulting
  [AI plan](../development/ai-implementation-plan.md) selected local CPU E5-small
  and an owner usage page. This historical provider baseline is superseded by the
  2026-10-21 decisions below. It was a planning request, not runtime/deployment authorization.

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
The 2026-10-21 answers below resolve the AI product policies and task identity;
actual account settings and per-grant execution parameters are implementation gates.

## Owner-confirmed AI specification (2026-10-21)

The owner supplied the complete functional draft and requested collaborative specification,
not runtime implementation. All rows are target behavior, not existing capabilities.
Selected-by-delegation rows record decisions the owner explicitly asked the agent to make.

| ID | Decision and evidence | Consequence |
| --- | --- | --- |
| AI-D-01 | Full draft selects multi-chat/tools, RAG, notes, extraction, planning/replanning, confirmation, grants, instructions and proactive reviews. | [AI product scope](ai.md) owns all selected scenarios; stage dependencies must not silently remove features. |
| AI-D-02 | Provider-neutral APIs; owner wants operator offerings and users' own model/API choices (answers 9/10). | No required Groq/DeepSeek/GLM model; separate supported adapters, operator catalog and encrypted owner-only personal credentials. |
| AI-D-03 | Using AI is agreement to relevant provider processing; no per-read permission dialogs. | Send necessary messages/source excerpts only, identify selected provider; write grants/other-user access remain separate. |
| AI-D-04 | RAG first; disclose missing local evidence, then general model knowledge and web search as needed (answer 1 and explicit follow-up). | Add bounded web search with real citations; do not fabricate local/private facts or treat tool failure as no evidence. |
| AI-D-05 | Separate chats, 30 days after last user message; explicit confirmation of that clock. | New user message renews; viewing/background work does not. Delete chat content/checkpoints together; preserve created objects. |
| AI-D-06 | Content-free activity retention is 30 days (answer 11). | Retain minimal replay/revocation protection independently; no hidden retained prompts. |
| AI-D-07 | Independent tasks, optional note links, no automatic checkbox synchronization (answer 2A). | Resolve Q-07; real task state owns completion. |
| AI-D-08 | AI may label/propose editable unknown-duration estimates (answer 3A). | Estimates are assumptions in preview, never source facts. |
| AI-D-09 | Explicit work windows; editable initial 45/15-minute work/break settings (answer 4A). | Ask for missing windows; structured constraints remain authoritative. |
| AI-D-10 | General replanning moves task sessions only; personal events need a direct request (earlier answer A). | Protect appointments/training and official occurrences. |
| AI-D-11 | Changed preconditions reject the whole plan and require a new preview (earlier answer A, reconfirmed). | Atomic application/outcome with availability/version serialization; no partial application. |
| AI-D-12 | Owner delegated stale-schedule choice (answer 5). Selected conditional preview only; affected application waits for freshness/coverage revalidation. | Preserve warnings; missing data cannot prove availability. Exact thresholds belong to P-06 contracts. |
| AI-D-13 | Owner requested settings-based assistant instructions (answer 6). | Editable personal instructions guide behavior below immutable server rules; hard work preferences are structured/versioned. |
| AI-D-14 | Owner delegated automatic-write policy (answer 7). Selected new-page/new-task creates in chosen scopes only. | Actual grants need operation/target/parameter/count/expiry/trigger; edits/moves/deletes stay confirmed. No grant was issued here. |
| AI-D-15 | Proactive features off until user configures them (answer 8A). | Opt-in schedule/frequency, existing in-app delivery, bounded/deduplicated quiet unchanged runs. |

The original draft selects one LangGraph agent with PostgreSQL checkpoints, neutral
Pydantic/tool contracts and deterministic planning. [ADR 0009](../adr/0009-specify-provider-neutral-ai-orchestration.md)
records boundaries and added complexity. Dependency/runtime compatibility is not verified.
OR-Tools/reranking/external tracing are conditional candidates, not automatic installations.

Actual vendor/model IDs, feature compatibility, API/search endpoints, account prices/quotas,
configured budgets, encryption details and replay purge are verified in the implementing
stage. These do not reopen the selected functionality or authorize external calls now.

## Remaining decisions

### Manual P-06 scope confirmed on 2026-10-21

The owner selected backend-only incremental delivery, exact offset-aware deadlines,
manual scheduling, advisory dependencies and page-only source links. Completing a
parent requires closed active subtasks. Task removal uses recoverable branch trash;
completion/cancellation/trash cancels future work blocks. Creation/moves are future-only.
Availability windows are supplied per request. Overlaps and uncertain official sources
require explicit acknowledgement and revalidation. AI and automatic scheduling are
not part of this delivery. Basic task create/read/update is the first implementation
increment; hierarchy, trash, dependencies, blocks and availability follow separately.
See [task contracts and actual status](../development/tasks.md).

On 2026-10-25, the owner confirmed the planned subtask invariants: optional
same-owner parent, no product-level depth limit or cycles, no edit propagation,
closed descendants before parent completion, no later active descendant beneath a
completed ancestor, and atomic validation of combined parent/status updates.
The hierarchy remains not implemented; see the [subtask contract](../development/tasks.md#confirmed-subtask-hierarchy-contract-2026-10-25).

| ID | Question | Proposed default | What depends on it |
| --- | --- | --- | --- |
| Q-04a | Product policies resolved in the 2026-10-21 table above. Per-account budgets/quotas and per-grant scope/expiry/counts are required activation inputs. | Provider-neutral operator/BYOK models, relevant-data transfer implied by AI use, 30-day chat/activity policies, initial automatic new-page/task creates only under actual grants. See [AI scope](ai.md). | Concrete credential/vendor contracts, execution records, minimal replay-record purge and account admission |
| Q-05 | Beyond mandatory database calendar views, which calendar features are required first: all-day events, recurrence, multiple calendars or external providers? | Existing timed events plus date projections; dates/deadlines are nonblocking. Recurrence/all-day contracts are separate; no Google/Microsoft sync assumed. | Date DTOs, recurrence/exception model and availability |
| Q-06 | Which history, purge and export features should follow recoverable trash? | Implemented branch trash restores its batch root and preserves previously trashed children; see [notes](../development/notes.md). No purge/history/export yet. | Future cleanup, history and export |
| Q-07 | Resolved on 2026-10-21: tasks are independent typed objects with optional source links. | Ordinary record rows/checkboxes are not tasks and do not synchronize status automatically. | P-06 task/subtask/dependency services and AI extraction/planning tools |
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
- AI execution: apply the confirmed 2026-10-21 policies; verify Q-04a account/grant parameters, idempotency and concrete vendor contracts before activation.
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
