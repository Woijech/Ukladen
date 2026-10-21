# Offline AI API

Updated: 2026-10-22.
Status: AI-01 step 6 implements authenticated fake-only transport, admission and
accounting. Disabled by default. Migration 0022 was tested on disposable databases;
it has not been applied to the running application. Real providers, workspace tools,
streaming, review/resume transport, restart reconciliation and physical retention
cleanup remain later work. See [the execution plan](ai-01-execution-plan.md).

## Configuration and composition

AI_ENABLED defaults to false. AI_LLM_PROVIDER and AI_LLM_MODEL accept only fake and
fake-v1 in this slice. Unsupported values fail configuration validation; no provider
fallback or model credentials exist. Enabling the flag exposes a synthetic demonstration,
not a useful general assistant: each normal turn calls fake_double with 7 and returns
the fixed answer `Offline test: 7 × 2 = 14.` It performs no workspace reads or writes.

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

All paths below are relative to /api/v1/ai. All responses, including errors, use
Cache-Control: no-store. Every operation requires an authenticated, active user with
completed registration. Mutations also require the existing allowed Origin and matching
CSRF cookie/header. Ownership is server-derived; request bodies reject unknown fields.

| Method / path | Input | Result |
| --- | --- | --- |
| POST /conversations | title, trimmed nonempty text up to 200 characters | 201 conversation metadata |
| GET /conversations | limit 1–200 (default 100), offset 0–2147483647 | items of nonexpired owned conversation metadata |
| GET /conversations/{id}/messages | after sequence 0–9223372036854775807, limit 1–200 | ordered message items after that sequence |
| POST /conversations/{id}/messages | submission_id UUID, message (nonblank, at most 16 KiB UTF-8) | 200 run metadata after foreground execution, or current state for a replay |
| GET /runs/{id} | Run UUID | Owned run state and content-free attempt/tool outcomes |
| POST /runs/{id}/cancel | No body | Current run state; terminal states remain unchanged |
| DELETE /conversations/{id} | Conversation UUID | 204; cancels active execution and cascades chat content |

Conversation metadata contains id, title, created_at and last_user_message_at.
Message items contain id, sequence, role, content and created_at. Current transport
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
conversation ID and exact message text. An exact owner-scoped replay returns the
existing run without another message/model call; a changed payload returns 409.
Replays do not renew chat activity. A second submission while a chat has queued,
running or interrupted work is rejected. Identity/submission protection survives
chat deletion through the independent journal.

Execution claims queued -> running in another short transaction. LangChain middleware
records each actual model dispatch before calling the fake model and its outcome
afterwards. Tool middleware records each attempted handler invocation and outcome;
validation failures are failed outcomes, not successful business writes. Limits are
4 attempts and 8 tool calls per run. No retry/fallback is configured. Missing usage
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

## Current recovery and retention limits

Viewing/assistant messages/replayed submissions do not extend the 30-day user-message
window. Expired chats are filtered or denied immediately. Physical content and journal
cleanup are not implemented yet; see [storage boundaries](ai-persistence.md).

If the process dies, checkpoint storage fails or final completion cannot commit, the
durably admitted run can remain queued/running with incomplete records. Reposting the
same submission does not dispatch again or fabricate completion. Cancel it to stop
pending work. Step 7 implements bounded execution and restart reconciliation; no
background recovery/timeout job or resume API is claimed here. This slice is not a
production release of the assistant.
