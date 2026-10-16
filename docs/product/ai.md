# AI Assistant Scenarios and Usage Analytics

Updated: 2026-10-17.
Status: planned; no AI runtime, AI UI, semantic index or usage dashboard is implemented.
This is the detailed AI product specification linked from [the product overview](overview.md).
Delivery order belongs to [the implementation plan](../development/ai-implementation-plan.md);
connection instructions belong to [the setup runbook](../development/ai-setup.md).
Preserve [WS-10](workspace.md#ws-10-ai-understands-and-acts-on-the-workspace) and
[ADR 0005](../adr/0005-support-scoped-ai-action-permissions.md).

## 1. Selected development baseline

The owner requested free Groq calls, interchangeable providers, local or free API
embeddings, an editable scenario catalog, staged setup instructions and AI usage analytics.
The host is the owner's laptop in Switzerland with 16 GiB RAM and a laptop RTX 4060.

The plan selects Groq `openai/gpt-oss-120b`, with `openai/gpt-oss-20b` for explicit
comparison, and local CPU `intfloat/multilingual-e5-small` embeddings. These are
development choices, not implemented integrations or paid-service authorization.
Use synthetic content until the external-content policy has been recorded.
Scoped automatic actions remain a confirmed future capability with unresolved limits.

## 2. Editable scenario catalog

Every row below is **not implemented**. "Selected" means included in this delivery
plan, not enabled in today's application. IDs remain stable when names/examples change.

| ID | Selection / stage | User request | Expected result and boundary |
| --- | --- | --- | --- |
| AI-UC-01 | Selected / AI-03 | What is on my calendar tomorrow? | Resolved events in the owner's timezone, with source freshness; no mutation |
| AI-UC-02 | Selected / AI-03 | Find my note about database normalization | Authorized lexical results and usable source references |
| AI-UC-03 | Selected / AI-03 | Summarize this selected page | Bounded current page content, citations and an explicit partial-content warning when needed |
| AI-UC-04 | Selected / AI-06 | Explain this topic using these materials | Cited retrieval from selected ready sources; unsupported answers are identified |
| AI-UC-05 | Optional / after AI-06 | Compare two complete documents | Coverage-aware processing of both documents; retrieved snippets alone do not establish complete coverage |
| AI-UC-06 | Optional / after AI-06 | Ask me questions about this lecture | Questions and feedback in chat; saving a page is a separate confirmed action |
| AI-UC-07 | Selected / AI-07 | Create a personal event tomorrow at 18:00 | Exact dated proposal, timezone, confirmation and normal event validation; no free-time claim |
| AI-UC-08 | Selected / AI-07 | Save this outline as a new page | Preview exact title/blocks, confirm, create one independent page |
| AI-UC-09 | Selected / AI-07 | Remind me before this event | Resolve an accessible event, show exact trigger, confirm one reminder |
| AI-UC-10 | Optional / after AI-07 | Move this event or replace this page section | Before/after preview and expected versions; whole-document block limits still apply |
| AI-UC-11 | Optional / after AI-03 | Show matching records in this database | Existing typed property/filter/view contracts; no arbitrary SQL or schema mutation |
| AI-UC-12 | Deferred / requires P-06 | Find free time and schedule my tasks | Availability/conflict/task services must exist before advertising this scenario |
| AI-UC-13 | Deferred / AI-08 | Automatically create pages in a selected collection | A separately chosen grant, operation scope, limits, expiry/revocation and explicit trigger |
| AI-UC-14 | Selected / AI-04 | Show how I use AI | Owner-only usage page, run details and honest cost/usage completeness |

To change scope, edit a row's selection and its acceptance example, then update the
corresponding stage and tool allowlist. Removing a scenario does not delete pages,
events, reminders, chats or execution history. Editing this Markdown file does not
change a running deployment.

Use a small server-side capability allowlist, not a user-programmable workflow engine:
`calendar_read`, `workspace_search`, `page_read`, `material_read`, `database_read`,
`event_create`, `page_create`, `reminder_create`. Introduce each value only when its
stage exists. Scenario selection can narrow this list; it cannot grant permissions.
Several scenarios can share a capability, so removing a shortcut is distinct from
revoking its underlying tool. Check current capabilities when advertising tools,
dispatching them and confirming/automatically executing pending actions.

## 3. Interaction requirements

- Planned entry points: `/workspace/ai` and a contextual panel beside the calendar.
- Explain the selected source scope before submission. Start with selected sources;
  any broader search is explicit and remains owner-filtered.
- Show sources in a read-only detail panel until canonical page/material UI exists.
  Do not link to nonexistent routes or require a full rich editor for this slice.
- Show useful progress states and cancellation; do not expose private model reasoning.
- Distinguish answer generation, an unconfirmed proposal and a committed change.
- Ambiguous dates/targets require clarification. Never merge lectures/labs by label.
- Questions and recommendations do not change business data. Conversation/usage
  persistence is disclosed separately from business actions.
- Cancellation prevents further work; it does not undo an already committed action.
- General explanations and workspace-derived facts must be distinguishable.

## 4. Usage page

Selected design: a dedicated `/workspace/ai/usage` page, linked from the assistant,
plus a compact per-run summary in chat. All routes here are planned, not existing.
No external analytics service or new administrator role is required.

| Page area | Required information |
| --- | --- |
| Summary | Runs, successful/failed/cancelled/interrupted runs, provider attempts, input/output tokens, cost status |
| Daily chart | Runs and tokens for 7/30-day presets, grouped in the user's timezone; accessible table equivalent |
| Model comparison | Provider/model, attempt count, reported tokens, median/p95 completed duration and sample count |
| Tool/action results | Read calls, rejected calls, proposals, confirmed/committed/failed/stale actions; separate denominators |
| Recent runs | Time, safe scenario ID, model, duration, token completeness, outcome, sanitized error category |
| Index state, after AI-06 | Owner's ready/pending/failed sources, last indexed version and retry guidance |

Run details show safe tool names/status/duration and action outcomes. Titles, prompts,
arguments and excerpts are not analytics fields. Opening a conversation or source
uses its separate ownership checks. Mark fake-provider traffic explicitly and exclude
it from the default real-provider totals.

Metric rules:

- A run is one user submission; an invocation is one provider attempt. Retries add
  invocations without inflating the number of user submissions.
- Provider-reported usage is authoritative for tokens. Missing usage is `unknown`,
  never zero. Display known totals together with the number of incomplete attempts.
- Reasoning tokens may already be part of output; cached tokens may be part of input.
  Preserve components without double counting and document provider mappings.
- Display free-plan expected spend separately from optional list-price estimates.
  Neither is an invoice. No provider invoice integration is planned initially.
- Estimated prices carry currency, effective date and the price snapshot used at
  invocation time. Current prices do not rewrite historical estimates.
- Quota limits belong to the shared provider account. A user's local usage cannot
  establish global remaining quota. Keep account-wide headers/limits in operator
  diagnostics; do not expose other users' consumption or credentials.
- Success means the relevant operation completed. A fluent answer does not prove
  factual correctness; quality comes from evaluations and optional user feedback.

## 5. Privacy, lifecycle and exclusions

All conversation, usage and action data is owner-scoped. Analytics responses use the
existing authenticated/no-store contracts. User content is excluded from diagnostics.
Recheck access to sources before reusing older tool results in a new turn.

Selected prototype retention defaults: 30 days for conversations/messages and 90 days
for content-free run/invocation/tool metadata. Explicit chat deletion removes its
content directly; recoverable chat trash is not selected. Do not silently store
deleted chat text in summaries.
Execution audit/grant retention must be decided before AI-07/08; cleaning a chat must
not erase an active idempotency record or enable a duplicate action. Confirm the
real-content policy and retention behavior before enabling private-content testing.

Not selected initially: paid fallback, public web fetching/search, hosted code tools,
voice, OCR, private IIS, collaboration, fine-tuning, automatic event moves/deletes,
bulk destructive actions, global user analytics and a general plugin marketplace.
These exclusions do not remove the owner's confirmed future automatic-action scope.

## 6. Product acceptance

- The selected scenarios work without an academic profile except where a request
  explicitly needs official schedule data.
- Every displayed source opens authorized current content or an honest unavailable state.
- An ownership change, trash or stale version cannot be bypassed through chat history.
- Disabling a capability blocks pending execution as well as new tool advertisement.
- Usage totals remain honest through retries, missing final stream usage and crashes.
- Another user cannot read any conversation, analytics aggregate or index status.
- The owner can adjust the catalog without a schema change unless the requested
  behavior genuinely introduces a new data or authorization contract.
