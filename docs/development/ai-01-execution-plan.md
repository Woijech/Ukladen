# AI-01 Execution Plan and Approval Checkpoints

Updated: 2026-10-24.
Status: in progress. Steps 1 through 7 are complete within their approved scope;
persistence migrations are tested only on disposable data, not applied to the app.
Steps 8/9 are not approved or implemented.
The owner requested approval before
changes and clarified that read-only inspection/checks need no additional permission.
This is a developer workflow, distinct from the
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
Obtain an explicit owner reply before the next step that changes the project or data;
read-only inspection/checks need no additional approval. If a step needs materially
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
model API call or deployment was executed during that preparation update. The first
implementation approval was pending then; subsequent progress is recorded below.

## 12. Delivery progress (2026-10-22)

Step 1 inspected the actual auth/registration/CSRF, synchronous SQLAlchemy transactions,
Alembic metadata/head, Celery cleanup/recovery and safe logging boundaries. No project
files or databases changed in that step.

Step 2 proved LangChain 1.4.7, langchain-core 1.6.13, LangGraph 1.2.16,
langgraph-checkpoint 4.3.0 and PostgreSQL checkpointer 3.2.0 on Python 3.14.4 with
Pydantic 2.13.5/Psycopg 3.3.6. Exact existing runtime pins initially failed resolution:
langgraph-sdk requires websockets <17 while Ukladen locked 17.1. Replacing only that
existing pin with 16.1.1 made the installation compatible; all other runtime pins
were preserved. There are 26 added runtime distributions on the tested Linux target.

Six phases in separate disposable Python containers passed: checkpoint setup/typed
input rejection, two review pauses, approve after restart, reject after restart and
history/deletion/SQLAlchemy verification. The synthetic tool ran once on approval
and zero times on rejection. External network was blocked in the proof script.
The proof used a separately named PostgreSQL 18.6 container with tmpfs data; its
container, data, temporary environment and package cache were removed. No existing
application database was used. This is framework evidence, not owned application
persistence or an authorization/idempotency proof.

Step 3 adds only the proven package versions and a fake-only internal harness;
see [the implemented subset and limits](ai-setup.md#a1-implemented-offline-harness).
It does not connect the harness to HTTP, Celery or business services. Framework
objects stay in the infrastructure/integration packages; the application exposes
AgentRunner and neutral Pydantic DTOs. A small result middleware also sanitizes
validation failures returned by ToolNode, which do not pass through exception-only
error handling. Built-in error/review/call-limit middleware owns the standard flow.

Step-3 verification: Ruff check and format check across the backend (370 files),
full Pyright (zero errors), 26 offline AI tests, full pytest (988 passed / 553 skipped),
uv lock --check --offline, uv pip check (94 installed packages), Markdown local
links/anchors/fences, git diff --check and docker compose config --quiet. The full
pytest run used the host execution context because sandbox TestClient setup hung;
PostgreSQL/Redis/S3 integration environment variables were explicitly unset. Native
integration tests were skipped, not passed. The owner separately approved adding
one non-null browser-cookie assertion in the existing Google-link test to fix its
pre-existing Pyright error; its native scenario remains among the skipped checks.

No migration, owned persistence/API, real provider call, business action, frontend
change, push or deployment was performed. Step 4 remains a separate approval:
implement owner-scoped persistence/checkpointer integration and prepare reviewed
migrations without applying them to existing application data.

Step 4 was subsequently approved. It adds domain state, a neutral repository port,
SQLAlchemy repositories and an owner-bound PostgreSQL checkpointer, plus the unapplied
0022_ai_persistence revision. See [persistence contracts and migration impact](ai-persistence.md).
The migration creates five application tables and four pinned checkpoint tables;
it does not update existing user data. Composite owner keys, ordered message admission,
versioned run transitions, submission uniqueness and a partial active-run index define
the storage constraints. Attempt usage is nullable rather than fabricated as zero.

Checkpoint access checks an active owner and a conversation within its 30-day window
inside each short storage transaction. Automatic setup and inherited unscoped deletion,
copying and pruning are disabled. No application service, API or worker invokes this
composition yet. Admission, durable accounting hooks, cancellation and cleanup remain
later steps. Static SQL generation and mocked cursor tests are not native PostgreSQL
constraint, concurrency or restart evidence.

Step-4 verification: 54 offline AI tests passed; full backend pytest reported
1016 passed / 553 skipped with native PostgreSQL/Redis/S3 targets unset. The full
run used the host execution context for local TestClient support and disabled remote
AI tracing. Ruff check, format check (380 files), full Pyright (zero errors), quiet
Compose validation, git diff --check and seven Markdown files/145 local links,
anchors and balanced fences passed. Skipped native checks were not counted as passed.

Step 5 requires separate approval: apply the prepared revision only to an explicitly
identified disposable database, verify migrations/metadata/ownership/rollback and
prove owned checkpoint resume across processes. No migration was applied during step 4.

Step 5 was subsequently approved. Native tests create separate committed schemas
on the explicitly disposable database ukladen_ai01_step5 in the no-network container
ukladen-ai01-step5-20261022 (PostgreSQL 18.6). The source, dependencies and exact
Python 3.14.4 runtime are mounted read-only into separate test containers. Database
storage is tmpfs; no existing application database, credentials or volume is reused.

The new test suite covers preserving upgrade, populated-downgrade refusal, composite
owner foreign keys, submission/active-run uniqueness, bounded attempts/tools/content,
unknown usage, stale run versions, message/checkpoint rollback, exact expiry and
active-user checks. Concurrent message/run admission accepts one contender. A guarded
checkpoint transaction blocks concurrent deletion; deletion then cascades content and
prevents recreation. The execution journal survives chat deletion and is removed by
owner deletion.

Fresh-process tests pause the fake agent and start new Python interpreters for foreign
owner rejection, approve/reject resume, stale review rejection and deleted-chat denial.
The tool executes once on approval and zero times on rejection. These are synthetic
checkpoint continuity checks, not business authorization or HTTP lifecycle evidence.
No runtime implementation or migration repair was needed; changes add durable native
tests and update implementation status. The initial full native attempt exhausted a
384 MiB temporary data disk; it was discarded and repeated with a 1 GiB tmpfs and
64 MiB WAL target while retaining normal fsync.
A later container-only import failure in credential-scrubbed document-parser children
was resolved by preserving the original virtualenv/interpreter mount paths, without
changing application code. Its 13 focused extraction tests then passed.

Final step-5 verification: full backend pytest with AUTH_TEST_DATABASE_URL and
AI_TEST_DATABASE_URL pointing only to that disposable target reported 1199 passed /
398 skipped (214.35 seconds), including all 28 new native AI cases and the existing
migration round-trip/metadata check. Other integration targets were unset. Ruff,
format (382 files), full Pyright (zero errors), quiet Compose validation, seven
Markdown files/146 local links and anchors, balanced fences and git diff --check
passed. No new runtime dependency was added. Test schemas were absent after the run;
the disposable database/container and its tmpfs storage were removed, and existing
application containers remained running. No application database migration, provider
request, push or deployment occurred.

Step 6 requires separate approval: implement the authenticated offline chat/run API,
durable request admission, submission idempotency and actual attempt/tool recording.
Cancellation/deletion transport is included in that step; recovery bounds and cleanup
remain steps 7/8. No real provider, business write tool, frontend, push or deployment
is authorized by step 5.

Step 6 was subsequently approved. It adds the authenticated, default-disabled
[offline API](ai-api.md), application lifecycle/transaction ports, framework accounting
middleware and pooled owned runner composition. No new dependency or migration is
needed. The existing session/registration/Origin/CSRF/no-store contracts are reused.
Admission and the user message commit together; owner-wide submission replay does
not dispatch again. Model/tool records commit around actual dispatch; unknown usage
remains nullable. Final assistant content and run completion share one transaction.

Cancel/delete mark active execution terminal before allowing further work. Bound
checkpoint access rejects cancelled runs, and a new turn selects its own/current or
the latest completed predecessor checkpoint. Native tests complete a newer run while
the cancelled model call is still blocked, then verify that its late result cannot
write an assistant answer. This is ordinary cancellation/continuation, not automatic
crash recovery. Failed completion can leave durable running work; exact replay returns
that state without repeating calls. Step 7 still owns restart reconciliation/timeouts.

The isolated test target is ukladen_ai01_step6 in ukladen-ai01-step6-20261022, with
Redis in ukladen-ai01-step6-redis-20261022 sharing its no-network namespace. PostgreSQL
uses tmpfs and normal fsync; Python/source/dependencies are mounted read-only using
their original paths so credential-scrubbed parser children work. No live application
database/cache, model credentials, SMTP delivery or external provider is involved.

Step-6 verification: all 109 AI tests passed against the finalized code, including
23 HTTP cases, 28 native persistence cases and four new accounting unit cases. The
default full backend suite passed 1020 tests / skipped 604 with native targets unset.
Ruff, format (390 files), full Pyright (zero errors), quiet Compose validation,
14 Markdown files/271 local links and anchors, balanced fences and git diff --check
passed. No frontend or real provider execution was needed.
All test schemas were absent after verification; both temporary service containers
and their RAM storage were removed. Existing application containers remained running.

An initial broader PostgreSQL/Redis run before the final six input-boundary cases
reported 1611 passed / 3 skipped / 4 failed. All four failures are the pre-existing
profile test's invalid/unknown cookie setup; a read-only source snapshot of commit
8b92d75 reproduced the same failures without the AI change. A temporary-snapshot
one-line removal of the original cookie before replacement made those four pass.
At that checkpoint the repository's unrelated test remained unchanged pending
separate owner permission; that initial broader run was not fully passing.

The owner subsequently approved the separate profile-test correction. The test now
deletes the original session cookie before setting an invalid/unknown replacement;
application authentication code is unchanged. All 39 profile HTTP tests passed on
the isolated PostgreSQL/Redis target after this one-line correction.

Final verification after the approved correction: the full backend suite passed
1621 tests / skipped 3 in 325.30 seconds with both native database URLs and the
test Redis URL pointing only to the disposable services. Ruff, format (390 files),
full Pyright (zero errors), quiet Compose validation and git diff --check passed.
Skipped checks are not counted as passed. All test schemas were absent afterward;
both disposable containers and their storage were removed, and existing application
containers remained running. No application database migration or external provider
call occurred. Step 7 remains unapproved.

Step 7 requires separate approval: bound execution time and retries, reconcile
unfinished runs after restart and verify recovery/cancel/interrupt races against the
durable ledger. Public review/resume behavior must preserve exact ownership and
budgets. Physical 30-day purge remains step 8; real providers/UI/business tools remain
separate stages. Do not enable the module or migrate existing application data here.

Step 7 was subsequently approved. Built-in ModelRetryMiddleware permits at most one
ConnectionError retry with a short fixed delay. Dispatch middleware and the durable
journal enforce four actual attempts including retries; tools and uncertain timeouts
are not retried. The owned run has a 60-second admission deadline and each tool a
10-second deadline capped by remaining time. Journal admission, checkpoint access
and final completion recheck the durable deadline. No custom model/tool loop,
provider fallback, SDK retry, dependency or migration was added.

A bounded synchronous call pool admits eight outstanding calls per process without
an unbounded queue. A timed-out call may keep its thread until it returns; late
outcomes cannot overwrite terminal journals, write answers or resume the graph.
This bounds dispatch waiting, not all database/metadata HTTP latency or arbitrary
side effects. Pure fake tools only remain registered; real adapters need transport
deadlines/cancellable execution, including bounded process shutdown.

The ai.reconcile_runs task is registered on the existing worker and scheduled every
30 seconds only when AI_ENABLED=true. Each sweep examines at most 100 overdue
queued/running runs. Owner-first locking, skip-locked admission and state rechecks
make concurrent/repeated sweeps safe, including disabled owners. Runs become failed;
unfinished attempts/tools become interrupted with unknown usage preserved. No model
request, tool action or uncertain checkpoint is replayed. Explicit HITL pauses and
terminal runs are preserved; pauses do not extend the admission deadline.

The process-termination test exits during a genuine fake-model dispatch, then starts
a fresh interpreter to reconcile the committed run. Exact submission replay returns
the stored failure without another dispatch; a new submission completes from safe
predecessor context. Native tests also cover exact deadline boundaries, rollback,
concurrent sweeps, busy owners, disabled owners, timeout/cancel/reconciliation races
with a still-blocked model, and durable budgets across fresh reviewed runners.
Framework approve/reject and stale/foreign/deleted review checks remain in the suite.
No public resume API or production action permission is introduced.

Step-7 final verification used ukladen_ai01_step7 in the no-network
ukladen-ai01-step7-20261022 PostgreSQL container, with Redis in
ukladen-ai01-step7-redis-20261022. Both services use disposable RAM storage and
read-only test clients; no live application database/cache is involved.

### Step-7 completion verification (2026-10-24)

After the interruption, the previous full-test process/output was unavailable.
The identified temporary services were restarted with fresh RAM storage; the full
suite was repeated rather than treating that unavailable result as passing.
Final backend pytest reported 1644 passed / 3 skipped in 338.87 seconds, including
all 132 collected AI tests. The three skipped checks require disposable S3/SeaweedFS
configuration (native file-job storage, material storage and avatar storage).

Ruff, format (397 files), full Pyright (zero errors), quiet Compose validation,
nine Markdown files/170 local links and anchors, balanced fences and git diff --check
passed. No frontend change/check was needed. Test schemas were absent afterward;
both temporary containers and their storage were removed. Non-test container state
was unchanged. No application database migration, real model call, push or deployment
occurred. Step 7 is complete within its approved offline scope.

Step 8 requires separate approval: physically purge chats/messages/checkpoints after
30 days of user-message inactivity and content-free activity after its own 30-day
window. Keep independent business objects and required minimal replay protection;
test exact boundaries, concurrent cleanup and non-resurrection. Step 9 final sign-off,
real providers, product UI and business tools remain separate approvals/stages.
