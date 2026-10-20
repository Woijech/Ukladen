# AI-00 Tool and Execution Contracts

Updated: 2026-10-21.
Status: specified, not implemented. This is the application contract beneath
[AI product requirements](../product/ai.md), not an existing API/SDK/tool registry.
Transport DTOs/migrations are finalized with each implementing stage. No real model,
web request or application mutation is authorized by these examples.

## 1. Common boundary

- Server context carries owner/session, run ID, connection/model profile, effective
  capabilities, current instant and profile timezone. None are overridable model arguments.
- Validate inputs/results with provider-neutral Pydantic DTOs; adapters own SDK conversion.
  Register only operations whose normal application services actually exist.
- Every reference has a discriminated source type/ID and version/location where
  applicable. Verify foreign IDs through ordinary services without leaking existence.
- Results declare safe status, bounded data, citations, read coverage/truncation,
  source freshness/index availability and safe error category. A failed/partial
  query is never indistinguishable from a successful complete no-match result.
- Tool content, files, instructions and web results are untrusted data. They cannot
  change owner, selected scope, capabilities, approval or credential connection.
- Search/read calls do not modify canonical user content. Usage persistence/provider
  traffic is explicit; proposal creation stores proposal state, not a business edit.
- Enforce limits before dispatch, not after accepting arbitrary provider arguments.
  Cancellation/deletion/credential revocation stops future dispatch including queued work.

## 2. Planned tool catalog

Names align with existing page/workspace vocabulary. The draft's search_notes and
search_materials map to source-filtered search_workspace; read_note maps to read_page.
Reading official schedule uses resolved calendar data rather than a duplicate path
that loses personal overrides. Schema version for the initial contracts is v1.

| Tool / capability | Minimum input | Result / effect | Required application support |
| --- | --- | --- | --- |
| search_workspace / workspace_search | Query, optional source types/explicit IDs, bounded limit/cursor | Authorized matches, citations, coverage and index state; read | Existing lexical search; hybrid after AI-06 |
| read_page / page_read | Page ID, optional block range, byte limit | Current blocks/version and actual read coverage; read | Notes read application interface |
| read_material_excerpt / material_read | Material ID, optional fragment/offset range, byte limit | Ready extracted text/version/location, partial flag; read | New bounded authorized extracted-text port |
| retrieve_context / retrieval_read | Query, optional selected source IDs, candidate limit | Current lexical/vector fragments, provenance and coverage; read | Search chunks/hybrid lifecycle AI-06 |
| get_calendar_events / calendar_read | Offset-aware range, optional personal/official type/title filter | Resolved events/overrides and coverage/freshness; read | Existing calendar query |
| query_database / database_read | Database/view ID, typed property filters/sort/cursor | Owned records/property schema with versions; read | Optional delivered workspace queries |
| get_tasks / task_read | Status/deadline filters, optional task IDs, cursor | Real task status/effort/dependencies/version; read | P-06 tasks, not a package marker |
| extract_tasks / task_extract | Authorized source refs or bounded submitted text | Task/subtask/deadline proposals with locations, estimates, uncertainty and possible duplicates; no task creation | AI-10 orchestration plus typed extraction DTOs |
| get_free_slots / availability_read | Range, allowed-window preference version, minimum minutes | Verified intervals with snapshot/freshness/coverage; read | P-06 full busy-set calendar interface |
| check_calendar_conflicts / availability_read | Proposed intervals, explicit edited target IDs | Real overlap set/warnings; read | P-06 calendar conflict application interface |
| generate_plan / planning_preview | Task IDs/versions, range, structured constraints/preference version | Feasible candidate sessions or unmet work, protected targets, calendar snapshot and assumptions; read/proposal only | P-06 deterministic task planner and AI-10 |
| get_user_preferences / preferences_read | Optional preference keys | Owned instructions and structured planning settings/version; read | AI settings; P-06 planning settings |
| search_web / web_search | Minimal query, optional language, result limit | Retrieved public URLs/titles/excerpts with retrieval time; external read only | AI-11 search application port and verified adapter |
| propose_action / per-operation write capability | Discriminated operation, exact target/parameters and expected versions/source refs | Immutable proposal ID/version, effects, expiry; no business mutation | AI-07 and delivered target application interface |

Proposal operations are explicit enum members: page_create, page_update, event_create,
event_update, reminder_create, task_create, task_update, relation_create and plan_apply.
Only delivered members are registered. Target relations must be real supported pairs;
no generic polymorphic association bypass. Page updates preserve block IDs/schema and
optimistic versions. Unknown operations, deletion and raw SQL/HTTP/code are rejected.
A collection choice is a reference operation, not permission to rewrite its members.

execute_approved_action is application-controlled execution, not a model tool that
accepts an approved=true argument. Owner confirmation comes through authenticated
CSRF-protected transport; automatic execution derives authority from a current matching
grant. Both use normal services and one durable idempotent execution path. Settings
and personal credential changes are likewise authenticated UI/application operations,
not unrestricted tools or model-generated credentials.

## 3. Initial execution budgets

These are implementation defaults for fakes/first adapters, not claims about provider
capacity. Effective limits are the minimum of configured application, model and account
limits. Operators may tune them after fixed-fixture measurements; account monetary
caps/terms are recorded before real activation. Unknown price/usage is not zero.

| Limit | Initial bound |
| --- | --- |
| Active runs | 1 per owned conversation |
| User message | 16 KiB UTF-8 |
| Provider attempts per run, including retries | 4 total; at most 1 retry for a retryable failed attempt |
| Complete tool invocations per run | 8 total |
| Provider input / output | 6000 / 2048 tokens per attempt, further reduced by verified model/account limits |
| Assembled source context | 48 KiB UTF-8 plus token limit; track coverage instead of silent truncation |
| One tool result | 16 KiB UTF-8, including bounded metadata |
| Retrieved fragments | At most 8 per context build; this does not mean a whole document was read |
| Tool / foreground run deadline | 10 / 60 seconds; return explicit pending/timeout if later stages introduce longer jobs |
| Web query / results | Query at most 512 characters; at most 5 results; excerpts count against tool/context bounds |

Input/output/reasoning behavior differs by model; failed evaluation can justify an
explicit profile adjustment, never unlimited retries or silently truncating a confirmed
mutation. Reserve budget for a final answer; stop safely with a partial/limit status
when remaining work cannot fit. Do not split a multi-action commit across model turns.

## 4. Proposal and plan consistency

A proposal includes owner, immutable operation list, parameter digest, targets and
expected versions, source references, applicable constraint/preference/capability
versions, availability snapshot, assumptions, effects and expiry. Technical initial
proposal expiry is 24 hours, also bounded by chat/source/connection validity; exact
storage/replay purge is finalized before AI-07. Expired/unknown proposal IDs never
become fresh executions. Changing payload requires a new proposal and confirmation.

Execute the whole plan and execution outcome in a shared database transaction. Recheck
all preconditions under serialization covering concurrent busy-event additions and
preference/task changes, not merely versions of events being moved. Any failure
rolls back the entire plan; report a new preview. Never wait for a model/network under
these locks. Notification/job publication follows a durable post-commit pattern.

Minimal replay/revocation records survive content cleanup only as needed; they contain
no prompts/documents. Chat deletion blocks pending execution and graph resume, preserves
committed business objects and cannot erase duplicate-execution protection.

## 5. Prompt and fixture versions

Initial identifiers: ukladen-assistant/v1, ukladen-source-grounding/v1,
ukladen-task-extraction/v1, ukladen-planning/v1 and ukladen-action-proposal/v1.
These name behavior contracts, not shipped runtime prompts. Owner instructions are
separate versioned user data below immutable server rules. Model/provider replacement
reruns the same scenarios without changing domain/tool semantics.

The [AI-00 fixture](../../apps/backend/tests/fixtures/ai/ai-00.json) contains synthetic
owners/sources, dates, planning input and acceptance cases with required/forbidden
outcomes. Case IDs are stable; ordinary CI will use fake provider responses when the
runtime exists. Static JSON/reference checks validate the fixture only; they do not
prove that AI, persistence, retrieval, transactions or UI currently work.

## 6. Required behavioral checks by stage

- AI-01/04: chat ownership, exact inactivity expiry, cancellation/restart, retained
  business objects, safe checkpoints, incomplete usage and streaming without replay.
- AI-02: operator/BYOK isolation, masked keys, disconnect during queued work, explicit
  model capability validation, quota/unknown cost and no silent credential fallback.
- AI-03/06/11: current-source citations, partial vs complete coverage, no-match vs
  failed reads, general/web labeling, no fabricated private facts, minimal search
  egress, injection resistance and no stale/foreign-source history reuse.
- P-06/AI-10: explicit task/checkbox separation, ambiguous old dates, labeled estimates,
  configured work windows, 45/15 preferences, DST, fixed events, infeasibility and
  atomic revalidation against concurrent new busy events.
- AI-07/08/12: exact confirmations/grants, revoked/expired/disabled tools, idempotency,
  whole-plan rollback, opt-in schedules, deduplication and quiet unchanged reviews.
