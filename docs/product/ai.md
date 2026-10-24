# AI Assistant Product Specification

Updated: 2026-10-24.
Status: agreed target specification. An [offline backend API](../development/ai-api.md)
implements the completed offline AI-01 foundation: fake chats/runs, accounting,
bounded recovery and 30-day cleanup, disabled by default and unmigrated in the app.
AI-02 adds an optional [OpenRouter catalog and encrypted personal connections](../development/ai-connections.md),
implemented locally but unactivated. [AI-03](../development/ai-03.md) implements backend
workspace/calendar/database read tools with lexical search and source references.
Chat UI, semantic retrieval, planning and usage analytics UI are not implemented. AI-00 specifies the target work; it does
not enable integrations. This is the single AI specification linked from
[the overview](overview.md). See [delivery](../development/ai-implementation-plan.md),
[architecture](../architecture/ai.md), [tool contracts](../development/ai-tool-contracts.md)
and [setup](../development/ai-setup.md).

## 1. Goal and confirmed scope

Connect the user's knowledge, unfinished work and available time through one assistant:
ordinary chat, grounded answers, note editing, task extraction, feasible schedules,
confirmed actions, scoped automatic creates, personal instructions and opt-in proactive
work. Academic examples never make an academic profile mandatory for personal use.

The owner's draft and decisions on 2026-10-21 select the full target below. Stages
express dependencies, not permission to omit selected features. DeepSeek, GLM and
other model families are examples of operator offerings, not mandatory providers,
verified model IDs or authorization to create accounts/spend money. The earlier
Groq-only baseline is superseded. LLM, embeddings and web search are separate adapters.

## 2. Editable scenario catalog

The full user experience in every row remains not implemented. AI-UC-20 now has
backend catalog/connection support; its settings UI remains AI-04. Existing IDs are preserved. Selected means target
scope, not a currently enabled tool. Database querying remains separately optional.

| ID | Selection / dependency | Request | Expected result and boundary |
| --- | --- | --- | --- |
| AI-UC-01 | Selected / AI-03 | What is on my calendar tomorrow? | Resolved events, profile timezone, overrides and freshness |
| AI-UC-02 | Selected / AI-03, AI-06 | Find my note about normalization | Authorized lexical/hybrid results and real source references |
| AI-UC-03 | Selected / AI-03 | Summarize this page | Current content, citations and explicit read coverage |
| AI-UC-04 | Selected / AI-06 | Explain this lab using my materials | Retrieved evidence; distinguish explanations and unsupported claims |
| AI-UC-05 | Selected / AI-06 | Compare these complete documents | Coverage-aware processing; top-k snippets do not prove completeness |
| AI-UC-06 | Selected / AI-06 | Ask me questions about this lecture | Questions/feedback; saving results is a separate action |
| AI-UC-07 | Selected / AI-07 | Create an event tomorrow at 18:00 | Exact date/time, preview and confirmed personal event |
| AI-UC-08 | Selected / AI-07 | Save this outline as a page | Exact title/blocks and one confirmed independent page |
| AI-UC-09 | Selected / AI-07 | Remind me before this event | Authorized target, exact trigger and confirmed reminder |
| AI-UC-10 | Selected / AI-07 | Improve this note or explicitly move this personal event | Before/after preview, current versions and exact confirmation |
| AI-UC-11 | Optional / existing workspace services | Show matching database records | Typed filters/properties; no SQL or schema mutation |
| AI-UC-12 | Selected / P-06, AI-10 | Fit my preparation before Friday | Deterministic feasible sessions and confirmed atomic application |
| AI-UC-13 | Selected, opt-in / AI-08 | Automatically create pages or tasks here | Scoped grant, trigger, limits and durable outcome; tasks also need AI-10 |
| AI-UC-14 | Selected / AI-04 | Show how I use AI | Owner-only usage, model comparison and honest completeness/cost status |
| AI-UC-15 | Selected / AI-10 | Extract assignments from my notes | Independent task proposals, source locations, deadlines and editable estimates |
| AI-UC-16 | Selected / P-06, AI-10 | Replan unfinished preparation | Move eligible task sessions only; protect other events and minimize changes |
| AI-UC-17 | Selected / AI-04, P-06 | Set my assistant instructions and work preferences | Editable instructions plus structured hard planning settings |
| AI-UC-18 | Selected, opt-in / AI-12 | Prepare a daily/weekly briefing | Bounded scheduled review, relevant notes and in-app warnings |
| AI-UC-19 | Selected / AI-11 | Explain this when my materials have no answer | State missing local evidence; use labeled model knowledge/web search as needed |
| AI-UC-20 | Selected / AI-02, AI-04 | Choose a model or connect my API | Operator offerings and owner-only personal credentials; no silent switching |

Removing a shortcut does not delete created objects. Check the server capability
allowlist during tool advertisement, dispatch and pending-action execution. Editing
this catalog does not change a deployment. Several scenarios may share a capability.

## 3. Chat and interaction

- Separate owner-scoped chats with ordered history, continuation and multi-tool requests.
- Planned entry points: /workspace/ai, contextual calendar panel and /workspace/ai/usage.
- Stream visible output/safe progress; support cancellation, stored state and reconnect
  without resubmission. Never expose private model reasoning.
- Distinguish answers, proposals, approvals and committed results. Explain useful
  reasons, assumptions and constraints rather than hidden reasoning.
- Show sources/action results. Use a bounded read-only source viewer until canonical
  page/material UI exists; no nonexistent links or arbitrary HTML.
- Errors are sanitized/actionable. Empty search, incomplete indexing and unavailable
  tools are distinct. Cancellation stops new work; it does not undo committed changes.

## 4. Retrieval and knowledge fallback

For workspace/material questions, search available relevant user sources first. The
assistant chooses registered tools within the request. An explicit instruction to
use only a selected document prevents silent expansion. General questions need not
scan unrelated private records.

Use semantic/full-text retrieval with deterministic rank fusion; add reranking only
for measured benefit. Support extractable PDF, DOCX, PPTX, TXT and Markdown, selected
sources, multiple documents, definitions, requirements, comparisons, summaries and
study explanations. OCR and arbitrary bookmark fetching remain excluded.

Source-backed claims cite real source IDs/versions and available block/fragment
locations. Never invent PDF pages. Full-source summaries/comparisons require recorded
coverage, bounded incremental reads or a partial-result warning. Top-k retrieval
cannot prove that every mention or requirement was found.

If local evidence is insufficient, say so before using general model knowledge and
public web search as needed. Distinguish local evidence, external evidence and
suggestions; cite retrieved web pages and never fabricate references for model
knowledge. External knowledge cannot establish private completion, deadline or
availability facts. Web search is a bounded application tool behind its own adapter:
minimal search terms, not whole private notes/history, and untrusted results.

A permission denial, unavailable index or failed read is not a successful empty
search. Report what could not be checked. Knowledge fallback never silently changes
LLM providers, credentials or billing sources.

## 5. Notes, tasks and relations

Support note creation/titles, spelling/grammar, rewriting, shortening/expansion,
structured outlines/lists, key ideas, summaries, related-source suggestions and study
questions. Persist edits through existing block/version contracts after authorization.
Relations remain explicit choices; equal subject labels never merge notes/lectures/labs.
Page-page/task links require application support before a tool can create them.

Tasks are independent typed objects with status, priority, optional deadline/effort,
subtasks/dependencies and optional source links. Checkboxes/database rows are not
automatically tasks and do not synchronize completion. Extraction proposes tasks,
possible duplicates, subtasks, priorities and durations before confirmed creation.
Source-stated values and AI estimates are distinct. Unknown duration may be estimated,
visibly labeled and edited in the plan preview. Passing a session does not prove work
completion. Use real task status/user input, not absence of a report, as completion evidence.

Ambiguous dates/targets require clarification or an unresolved value. Interpret relative
dates using source context/timezone; Friday in an old note is not automatically next Friday.

## 6. Calendar and deterministic planning

Calendar reads preserve official facts, personal overrides and freshness/coverage.
Hidden busy events remain occupied; skipped/nonblocking events do not. Deadlines are
nonblocking until work is scheduled. Official occurrences are not personal editable events.

Calendar services compute occupied/free intervals and conflicts. Tasks owns a planning
application service using deadlines, dependencies, priorities, effort, allowed hours
and breaks. LLMs interpret requests/explain results; algorithms establish feasibility.

Users set allowed work windows; ask when absent. Initial session/break defaults are
45/15 minutes, editable. Exact deadlines/protected time/restrictions are hard constraints.
Offer alternatives and explain unmet work when infeasible; never silently violate them.
Among feasible plans, respect deadlines/priorities and minimize existing-session changes.

Normal replanning moves only eligible unprotected task sessions. Personal appointments
and training stay fixed unless directly requested; official events stay fixed. A
passed/missed session does not silently complete its task.

Under owner-delegated policy, stale/missing official coverage permits only conditional
previews with warnings. Applying affected plans requires successful freshness/coverage
revalidation; unknown coverage is never confirmed free time. This does not invent an IIS API.
Only configured/expected sources require such coverage; a user without an academic
profile can plan around personal data without needing university schedule coverage.

## 7. Proposals, confirmation and automatic actions

Support read-only help, recommendations, exact confirmed actions and scoped automatic
actions under [ADR 0005](../adr/0005-support-scoped-ai-action-permissions.md).
Confirmation binds immutable targets, parameters, versions, constraints, effects and
expiry to the owner. Edits invalidate previous confirmation. Pending state survives
restart; rights, versions, source state and current capabilities are checked again.

A multi-action plan and its execution outcome commit atomically in one database
transaction. Any changed target, constraint or relevant calendar state means apply
nothing, report conflict and request approval of a new preview. Availability/version
serialization is required; graph checkpoints do not provide business atomicity.

Under owner delegation, initial automatic writes are new-page/new-task creation in
selected scopes. Task tools need AI-10. Existing-content edits, event/session moves
and deletes remain confirmed actions. This allowlist is not a real grant. Each actual
grant needs authenticated owner configuration: operation, target/parameter limits,
count limits, expiry and explicit trigger. Revoked/expired/out-of-scope grants fail.
Content/model arguments/instructions cannot create or broaden permissions.

## 8. Instructions, preferences and proactive work

Provide a personal assistant-instructions field in settings for tone, detail and
preferences. It cannot replace server authorization, identity, tool validation,
source restrictions or confirmation. Settings are saved by explicit user action;
ordinary messages are not automatically permanent memory.

Hard planning preferences remain structured/versioned: timezone, work windows,
session/break lengths and protected time. Free text may propose a setting change;
unresolved/conflicting instructions cannot override constraints. Users view/edit/delete
preferences independently of chats.

Proactive daily/weekly reviews, deadline/overload/conflict warnings and source suggestions
are off by default. Users choose timing/frequency. Reuse in-app notifications and
workers; other channels need a separate slice. Bound candidates/model calls, deduplicate
and skip unchanged non-actionable work. Disabling stops future runs. Read-only briefings
do not authorize writes; grants alone do not create recurring schedules.

## 9. Providers, credentials and usage page

Support both operator-offered models and user-owned API connections. Show the selected
provider/account before submission. Operators offer multiple supported adapters/models;
users select an offering or their own supported connection, including free models where
available. This specification guarantees neither a particular model nor a free quota.

Keys are server-side secrets. Operator keys are consumer-scoped deployment secrets;
personal keys require owner-only encrypted persistence and a deployment-managed
encryption key. Submit them through authenticated/CSRF-protected settings, never return
plaintext. No secrets in prompts, checkpoints, analytics, logs or bundles. Disconnect
blocks new/queued dispatch through that connection.

Interchangeability preserves tools, not identical provider features. Validate tool,
structured-output and streaming support before activation. Reject incompatible models
or explicitly limit modes; do not silently weaken behavior or switch credentials.
LLM, embedding and search credentials/billing are independent. SDK/framework types do
not enter domain/application contracts.

The planned /workspace/ai/usage page and per-run summary show owner-only 7/30-day
summaries, daily series/accessible tables, model comparisons, recent runs, safe tool/action
outcomes and index state. No new administrator role/global analytics is required.

- A submission is one run; genuine retries are distinct provider attempts.
- Reported usage is authoritative; missing usage is unknown, not zero. Preserve failed
  and cancelled attempt usage; avoid reasoning/output and cached/input double counting.
- Record provider/model, credential source (not key), price date/currency and historical
  estimates. Free-plan expectations, estimates and invoices are different.
- Shared provider quotas may include outside traffic; local usage is not global balance.
- Require bounded request/token admission and configured account spending policy before
  activation. Actual models, prices, monetary caps and quotas are activation settings,
  not spending authorization in this documentation task. No automatic paid fallback.
- Use existing safe diagnostics. OpenTelemetry/Langfuse are later observability candidates,
  not installed requirements or default destinations for private content.

## 10. Privacy and retention

Using AI is the product's default agreement to send messages and necessary relevant
source fragments to the selected provider, without per-read transfer dialogs. Explain
processing and source scope in the UI. This does not grant writes, other-user access,
whole-workspace export or unsolicited background execution. Provider retention is
separate from local deletion.

Revalidate source access/current versions before reusing tool bodies or derived
summaries. Trash/deletion/access loss cannot be bypassed through chat/checkpoints.
User content/secrets are excluded from diagnostics/usage by default.

| Data | Retention / deletion |
| --- | --- |
| Chats/messages and content-bearing checkpoints, tool context, summaries | 30 days after last user message; new user messages renew; viewing/background work does not |
| Manual chat deletion | Immediately deny access/resume and remove chat content/derived context; no chat trash |
| Content-free usage/tool/action activity | 30 days from each event, independent of chat activity |
| Explicit instructions/planning preferences | Separate settings until user edits/deletes; never reconstructed from deleted chats |
| Created pages/tasks/events/reminders | Their own module lifecycle; chat expiry/deletion preserves them |
| Minimal replay/idempotency/revocation records | Retain only what rejects duplicate/revoked actions independently of chat expiry; no prompts/document bodies |

Expired/deleted chats must be immediately inaccessible to reads/runs. Cleanup erases
all chat-owned copies and prevents queued work resurrecting content. Define backup/restore
handling before production. Finalize minimal replay-record purge with AI-07; analytics
cleanup must not make an old confirmation executable again.

## 11. Acceptance and exclusions

End-to-end example: find requirements for two Friday labs, read real unfinished-task
state, label effort estimates and suggest a feasible plan without moving training.
Show sources/effects, ask about ambiguity and explain infeasibility. Apply the whole
plan only after authorization/revalidation. Test owner isolation, injection, citations,
coverage/fallback, dates, disabled tools, cancellation, restart/replay, grants, credentials,
retention and usage. See [synthetic contracts](../development/ai-tool-contracts.md).

Not selected: private IIS/grades/write-back, OCR/audio/voice, collaboration, automatic
event moves/deletes, bulk destructive actions, arbitrary SQL/shell, hosted code tools,
unrestricted URL fetching and a plugin marketplace. Web search is selected through
its bounded adapter only. New features require a separate request.
