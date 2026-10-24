# AI Chat and Run API

Updated: 2026-10-24.
Status: the completed AI-01 foundation implements authenticated transport, admission,
accounting, bounded execution, recovery and 30-day cleanup. Disabled by default.
Migrations 0022/0023 were tested on disposable databases;
they have not been applied to the running application. AI-02 adds an optional
[model catalog and encrypted connections](ai-connections.md), disabled and unactivated.
[AI-03 source tools](ai-03.md) add authorized workspace reads and source references.
Live chat streaming and review/resume transport remain later work. See [the execution plan](ai-01-execution-plan.md).

## Configuration and composition

AI_ENABLED defaults to false. AI_LLM_PROVIDER and AI_LLM_MODEL accept only fake and
fake-v1 in this slice. Unsupported values fail configuration validation; no provider
fallback exists. Optional AI_CONNECTIONS_FILE supplies explicit real model offerings.
Without a selected offering, enabling the flag exposes a synthetic demonstration,
not a useful general assistant: each normal turn calls fake_double with 7 and returns
the fixed answer `Offline test: 7 × 2 = 14.` It performs no workspace reads or writes.

AI_RETENTION_ENABLED defaults to false. With the reviewed migrations applied,
keeping this flag true in worker/Beat continues recovery/cleanup when AI_ENABLED=false;
it does not expose the chat API or dispatch a model. Both flags false schedule no AI
maintenance and need no AI tables. Never enable either flag against an unmigrated database.

The ordinary API installer registers routes without connecting to AI storage or
issuing DDL. Applying the reviewed Alembic revision is an explicit prerequisite for
opting in. Existing deployments with the default flag do not access AI tables.

AiService owns the request lifecycle through AiTransactions and AgentRunners ports.
The SQLAlchemy transaction adapter rechecks an active owner, serializes writes with
the existing owner lock and commits only short operations. Authentication uses the
existing completed-registration session dependency. Model/tool execution has no
caller-held database transaction. The runner factory borrows an autocommit pooled
connection for checkpoint IO and restores its row factory/isolation on return.

## HTTP contract

AI-04 extends this transport with an additive streaming endpoint, latest-first
history windows, current source inspection, independent preferences and owner usage.
See [the implemented AI-04 contract](ai-04.md) for their inputs, event/privacy bounds
and recovery behavior. The existing synchronous submission endpoint is preserved.

All paths below are relative to /api/v1/ai. All responses, including errors, use
Cache-Control: no-store. Every operation requires an authenticated, active user with
completed registration. Mutations also require the existing allowed Origin and matching
CSRF cookie/header. Ownership is server-derived; request bodies reject unknown fields.

| Method / path | Input | Result |
| --- | --- | --- |
| POST /conversations | title, trimmed nonempty text up to 200 characters | 201 conversation metadata |
| GET /conversations | limit 1–200 (default 100), offset 0–2147483647 | items of nonexpired owned conversation metadata |
| GET /conversations/{id}/messages | after sequence 0–9223372036854775807, limit 1–200 | ordered message items after that sequence |
| POST /conversations/{id}/messages | submission_id UUID, message (nonblank, at most 16 KiB UTF-8), optional source_scope | 200 run metadata after foreground execution, or current state for a replay |
| GET /runs/{id} | Run UUID | Owned run state and content-free attempt/tool outcomes |
| POST /runs/{id}/cancel | No body | Current run state; terminal states remain unchanged |
| DELETE /conversations/{id} | Conversation UUID | 204; cancels active execution and cascades chat content |

Conversation metadata contains id, title, created_at and last_user_message_at,
plus the immutable model/connection selection described in [AI-02](ai-connections.md).
Message items contain id, sequence, role, content, created_at and sources. Sources
are bounded historical references to evidence used at generation, not fresh access
authorization or an assertion that every generated claim is supported. See [AI-03](ai-03.md). Current transport
persists user and final assistant messages; intermediate tool bodies remain solely
in conversation-owned checkpoints.

Run results contain id, nullable conversation_id, submission_id, provider/model,
status, version, timestamps, attempts and tools. Attempt entries contain number,
status/times, nullable input_tokens/output_tokens and a fixed error_code. Tool entries
contain number, call_id, tool_name, status/times and a fixed error_code. Responses
exclude user_id, submission digests, raw exceptions, prompts and tool arguments/results.
Get the answer through message history; POST does not return private graph internals.

Invalid input is 422; foreign/missing/expired chat IDs and foreign/missing run IDs are
404. Conflicting submission payloads or active execution are 409. Disabled AI/storage
outages are 503. Normal session/registration/CSRF failures keep their existing status.
Runs detached by chat deletion remain readable as content-free owned journal entries.
An expired existing chat denies run access as well as history and new submissions.

## Admission, execution and replay

A transaction checks owner, expiry, submission uniqueness and the active-run slot,
then records a queued run and its user message together. The digest includes both
conversation ID and exact message text, plus source_scope when supplied.
Omitted scope preserves the existing digest and unrestricted owned-source behavior. An exact owner-scoped replay returns the
existing run without another message/model call; a changed payload returns 409.
Replays do not renew chat activity. A second submission while a chat has queued,
running or interrupted work is rejected. Identity/submission protection survives
chat deletion through the independent journal.

Execution claims queued -> running in another short transaction. LangChain middleware
records each actual model dispatch before calling the fake model and its outcome
afterwards. Tool middleware records each attempted handler invocation and outcome;
validation failures are failed outcomes, not successful business writes. Limits are
4 actual attempts and 8 tool calls per run. Built-in ModelRetryMiddleware permits
one retry on ConnectionError with a 50 ms delay; both calls enter the journal and
consume the same attempt budget. Other errors, timeouts and tools are not retried;
no provider fallback or SDK retry is configured. Missing usage
stays NULL; measured zero remains zero. The answer and completed run state commit
together. Failure/limit outcomes are failed runs; internal HITL pauses are interrupted
but have no public resume endpoint yet.

Checkpoint operations additionally verify the bound running run. Checkpoint metadata
stores its server-issued ukladen_run_id. A new execution loads its own latest checkpoint
or the latest completed predecessor; failed/cancelled branches cannot supply unfinished
work to a new turn. This preserves framework history and permits a new run after
cancellation while the previous model call is still returning.

Cancellation immediately marks the run and unfinished attempt/tool records cancelled/
interrupted. It prevents further dispatch and checkpoint writes for that run. An
already admitted call may finish; its late result cannot append an assistant message,
change the terminal run state or overwrite a newer run's context. Deletion applies
the same barrier before cascading content. Independent pages/events are preserved.

## Execution deadlines and recovery

The owned execution deadline is 60 seconds from durable admission, including the
queued interval. Each synthetic tool has a 10-second deadline, further reduced by
the remaining run budget. Journal admission, checkpoint access and final completion
also reject work past the durable deadline. Metadata/database I/O is not a hard
real-time HTTP latency guarantee. Existing connection/pool/storage behavior still applies.

Synchronous handlers run in a process-wide pool with at most eight outstanding
calls and no waiting admission queue. Capacity rejection does not dispatch or create
a provider attempt. A deadline returns control without waiting for a stuck handler;
unfinished journal entries become interrupted with error_code=timeout. Python cannot
kill a running thread: its slot stays occupied until it returns, and process shutdown
can also wait for it. Its late result cannot complete the run, append an answer or
reopen the closed journal. AI-02 may fill reported token counts on an existing
unexpired interrupted attempt without changing its terminal status or retention clock. Native tests
exercise timeout, cancellation and reconciliation while that call is still blocked.
Only pure fake tools are registered. Real adapters/tools must supply bounded transport
timeouts or cancellable execution before activation; this is not isolation for arbitrary
code or a guarantee that a timed-out external write did not happen.

When AI_ENABLED or AI_RETENTION_ENABLED is true, Celery Beat schedules
ai.reconcile_runs every 30 seconds on the existing worker. All consumers use the
migrated database; API dispatch requires AI_ENABLED, and worker/Beat maintenance
requires either flag. The task processes at most 100 overdue queued/running records per sweep,
using owner-first locks and skipping busy owners. Repeated/concurrent sweeps are
idempotent, including for disabled owners. Runs at least 60 seconds old become failed;
unfinished attempts/tools become interrupted with error_code=interrupted and retain
unknown usage. Terminal runs and explicit HITL pauses are preserved.
An internal bound-run review does not renew its admission deadline; an expired pause
can be cancelled. Longer-lived product proposal/resume policy belongs to AI-07.

This conservative restart policy does not replay an uncertain model/tool call or
invent an answer from a checkpoint. Exact submission replay returns the stored failed
state; a new submission can proceed using completed predecessor context. Reviewed fake
interrupts still resume through the framework with explicit decisions, fresh ownership
checks and the durable attempt budget. There is no public resume endpoint or automatic
approval; the production action/review bridge remains AI-07.

## Physical retention and replay protection

Viewing/assistant messages/replayed submissions do not extend the 30-day user-message
window. Expired chats are filtered or denied immediately. The maintenance task also
purges at most 100 expired chats and processes at most 100 eligible journal runs per
sweep. It rechecks expiry under owner locks, cancels active/interrupted work, then
cascades messages and all three checkpoint content tables. Other pages/events/files
are preserved. Failure rolls back the current item; completed items remain deleted,
and a repeated/concurrent sweep is safe. Disabled owners are included.

Content-free run records expire 30 days after their terminal transition. Attempt/tool
records use their outcome time, or start time if the outcome is unknown, independently.
Reads and unrelated background activity do not extend these clocks. Cancellation
caused by expiry is a new content-free transition with its own 30-day window. Active-run counters are
never pruned; terminal parents are removed after their children expire. Expired journal
details are hidden immediately, even while physical cleanup waits for a worker.

Before purging a run, the same transaction leaves an ai_run_receipts row containing
only owner ID, run ID, submission ID and a completed boolean. These minimal replay and
committed-context markers last until account deletion; they contain no prompt, digest,
model label, usage, tool data or timestamps. An old submission ID returns 409 instead
of becoming executable after cleanup when reused in a valid owned chat.
GET for a purged/expired run returns 404.
Completed markers preserve the correct checkpoint context of a still-active chat;
failed/cancelled branches remain excluded. The markers cannot authorize an action.
See [storage and migration impact](ai-persistence.md).

If storage is unavailable, reconciliation waits for a later successful sweep. Worker
or Beat outages delay it; reads do not run maintenance. The feature remains disabled
by default and its migration is unapplied to the running app. This slice is not a
production release of the assistant.
