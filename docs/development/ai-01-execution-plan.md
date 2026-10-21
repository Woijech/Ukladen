# AI-01 Execution Plan and Approval Checkpoints

Updated: 2026-10-22.
Status: planned; none of the implementation steps below has been approved or executed.
The owner authorized this documentation update and asked to approve each subsequent
implementation step separately. This is a developer workflow, distinct from the
application's human-in-the-loop approval of user-data changes.

Read [the AI plan](ai-implementation-plan.md#5-ai-01-offline-orchestration-persistence-and-accounting),
[architecture](../architecture/ai.md), [ADR 0009](../adr/0009-specify-provider-neutral-ai-orchestration.md)
and [tool contracts](ai-tool-contracts.md).

## 1. Scope and approval rule

AI-01 delivers an offline backend foundation using LangChain create_agent, typed
tools, HITL middleware, LangGraph persistence and a deterministic fake model. Do not
write a second model/tool loop. Ukladen owns authenticated access, request lifecycle,
durable accounting, retention and later business authorization/transactions.

Approval of a numbered step covers its listed implementation, focused tests and
repairs inside that scope, plus a local checkpoint commit when the change is
self-contained and verified. At completion report changed files, executed checks,
limitations and the proposed next step, then stop. Silence/time passing is not approval.
Do not start the next step without an explicit owner reply. If a step needs materially
broader changes, explain the concrete change and obtain approval before that work.

No real LLM/search calls, API keys, paid usage, embeddings, P-06 planning, production
business tools, action/grant tables, AI UI, push or deployment belong to AI-01.
Do not apply migrations to existing application data in this workflow. Only separately
identified disposable test databases are allowed in approved test steps.

## 2. Step 1: inspect and propose the exact integration

After approval, inspect current code through CodeGraph and read only relevant config,
service/transaction/test patterns. Locate authentication/CSRF, settings, dependency
locks, database session/metadata/migration patterns, worker cleanup and safe diagnostics.
Read official framework/package metadata for current compatibility and APIs.

Deliver a concrete file/module map, minimal package candidates, proposed application
boundary, run/checkpoint ownership and migration/test outline. Avoid redundant wrappers
around LangChain components. Do not install packages, modify project code or databases,
run provider calls or proceed to a compatibility probe during this read-only step.

## 3. Step 2: prove compatibility in isolation

After separate approval, create a temporary environment and use synthetic input and
an identified disposable PostgreSQL database. Test candidate pinned LangChain,
LangGraph and PostgreSQL checkpointer versions under the current project Python.
Prove create_agent can use the fake model, call a typed test tool, interrupt for
approve/reject, persist and resume after a fresh process starts.

Report exact versions/dependencies, commands, pass/failure and cleanup. Repository
runtime/dependency files and existing application databases remain unchanged. External
package/document downloads are allowed by this step; model API traffic is not.
An incompatible result requires a concrete alternative, never a silent Python downgrade.

## 4. Step 3: add the tested dependencies and minimal agent

After approval, add only proven framework/checkpointer packages to backend dependency
configuration/lock. Explain package purpose and transitive complexity. Build the
infrastructure composition using create_agent, typed fake tools and deterministic
fake model; retain a narrow framework-neutral application contract. No custom graph
or provider wrapper hierarchy without demonstrated need.

Verify the offline model/tool exchange, input validation, tool errors/call limits
and fake HITL approval/rejection with focused tests. This does not enable production
write tools or real provider settings. Run applicable Ruff/Pyright checks on the change.

## 5. Step 4: implement owned persistence and prepare migrations

After approval, implement conversation/message, run, provider-attempt and tool-outcome
entities/repositories and integrate the tested checkpointer. Document owner keys,
ordered messages, run/submission uniqueness, safe metadata and deletion boundaries.
Keep provider secrets/framework objects out of application DTOs and persisted prompts.

Prepare Alembic migrations for both application and checkpoint schema, following the
existing metadata/transaction conventions. API startup must not issue automatic
framework setup DDL. Show schema changes and migration impact before applying them.
No action/grant tables and no migrations against existing data in this step.

## 6. Step 5: verify migrations and persistence on disposable data

After approval, identify the isolated test database explicitly, apply migrations and
test upgrade/downgrade/metadata consistency, constraints, foreign ownership and
transaction rollback. Prove checkpoint/thread ownership and resumption across restart.
Never reset shared volumes or reuse a live application database as disposable data.

Report native persistence checks and confirm the tested data scope. Repair migration
issues within this approved scope; do not apply the result to a real deployment.

## 7. Step 6: implement the authenticated request lifecycle

After approval, connect normal application services to planned /api/v1/ai endpoints:
chat create/list/history, message submission, run state/cancellation and chat deletion.
Use existing sessions, completed-registration, CSRF/Origin and no-store contracts.
Identity is server-derived; enforce owner isolation and bounded DTOs.

Integrate the framework/fake runner with durable admission, one active run/chat and
submission idempotency. Record each genuine model attempt and tool outcome; missing
usage stays unknown. No database locks across model execution. Check API ownership,
validation, duplicate submissions and run/attempt arithmetic with focused tests.

## 8. Step 7: bound execution and verify failure recovery

After approval, wire compatible built-in model/tool call limits and sanitized errors,
bounded retries/timeouts, cancellation and restart reconciliation. Disable hidden
retry/fallback that would bypass the attempt ledger. Use framework resume/checkpoint
mechanisms, not a second agent engine.

Test parallel submission, fake interrupt/resume, malformed tool calls, missing usage,
timeout/cancel races and interrupted runs. A checkpoint does not authorize future
business writes. Restore stored state without duplicate requests or fabricated success.

## 9. Step 8: implement 30-day retention and complete deletion

After approval, expire chats 30 days after the last user message; viewing, assistant
messages and background activity do not extend it. Keep content-free activity for
30 days from each event. Manual deletion/expiry covers all chat-owned messages,
checkpoint history, summaries/tool bodies and queued resume paths.

Reuse existing bounded cleanup/job patterns. Block access/new execution immediately
at expiry; cleanup/retry cannot resurrect deleted content. Preserve independently
owned pages/events/tasks and future minimal replay protection. Test exact time
boundaries, deletion during a run, cleanup replay and unchanged existing workflows.

## 10. Step 9: complete verification, documentation and local commit

After approval, run required backend Ruff/format, Pyright, pytest and applicable native
PostgreSQL/Redis checks plus base docker compose config --quiet. Validate the home
overlay if this stage changed its wiring. Ordinary tests remain network-free; no
frontend build is needed unless a separately approved scope included frontend changes.

Update implemented settings/API/setup/status and dated verification with actual results;
do not claim all 36 future scenarios work. Create a cohesive local English commit with
task-related files only and show the final status. Push/deployment are not authorized.

AI-01 is complete when these approved steps pass, and the owner can inspect an offline
owned API/model/tool/checkpoint lifecycle. AI-02 real providers, AI-03 business reads,
AI-04 UI and AI-07 production action approval remain separate requested stages.

## 11. Documentation preparation verification (2026-10-22)

Executed for this documentation update: 9 Markdown files/152 local links and anchors,
balanced fences, English additions, nine distinct approval checkpoints, preservation
of dated verification history, git diff --check and docker compose config --quiet.
No AI-01 compatibility probe, package installation, database migration, runtime test,
model API call or deployment was executed. The first implementation approval is pending.
