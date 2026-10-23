# AI Persistence Contracts

Updated: 2026-10-24.
Status: the completed offline AI-01 foundation implements and natively tests owned
persistence, authenticated fake-only API accounting, bounded recovery and retention.
The migrations have been applied only to disposable test schemas, never to the app.
The [HTTP lifecycle](ai-api.md) uses this storage when explicitly enabled; there is
no model worker dispatch; the existing worker performs bounded recovery/cleanup. Read the
[execution plan](ai-01-execution-plan.md) and [AI architecture](../architecture/ai.md).

## Schema and migration impact

[0022_ai_persistence](../../apps/backend/alembic/versions/0022_ai_persistence.py)
follows 0021_google_email_confirmations and creates nine new tables. It does not
rewrite existing users, pages, events or files. Existing user deletion gains cascades
over newly owned AI records. Applying the revision still requires normal migration
privileges and brief locks for constraints referencing users.

| Table | Stored data / constraints |
| --- | --- |
| ai_conversations | Owner, private title, creation/last user-message time and next sequence; unique generated text thread ID |
| ai_messages | Owner, conversation, role, ordered sequence, bounded text and timestamp; unique sequence within a conversation |
| ai_runs | Owner, optional conversation, submission ID/digest, provider/model labels, state, version and timestamps; owner-wide unique submission; at most one queued/running/interrupted run per chat |
| ai_provider_attempts | Owner/run, bounded attempt number, outcome/times, nullable token usage and safe error category |
| ai_tool_executions | Owner/run, bounded call number, unique call ID, tool label, outcome/times and safe error category |
| checkpoint_migrations | Applied pinned checkpoint schema versions 0 through 9 |
| checkpoints | LangGraph JSON state/metadata and checkpoint ancestry within an owned thread |
| checkpoint_blobs | Serialized graph channel state within an owned thread |
| checkpoint_writes | Serialized pending graph writes within an owned thread |

Composite foreign keys enforce message/run conversation ownership and attempt/tool
run ownership. The three checkpoint content tables reference the conversation's
generated text ID. Checkpoint binary columns contain serialized execution state;
uploaded files still belong in object storage.

The checkpoint layout mirrors langgraph-checkpoint-postgres 3.2.0 after its ten
migrations, with additional ownership foreign keys. New empty tables use normal
transactional index creation. Alembic seeds only the checkpoint migration register.
Both application and checkpoint tables participate in the backend metadata.
Upgrading the pinned package requires reviewing its schema and preparing a new
Alembic revision when necessary. API startup never calls PostgresSaver.setup().

Downgrade takes exclusive locks and refuses to drop tables while any AI conversation,
message, execution or checkpoint content remains. The version register alone does
not prevent an empty-schema downgrade. It does not silently delete populated AI data.
The guard and schema equivalence are covered by native PostgreSQL tests.

## Transactions and access

[0023_ai_run_receipts](../../apps/backend/alembic/versions/0023_ai_run_receipts.py)
adds one empty table with run_id, user_id, submission_id and completed only. It does
not backfill/rewrite existing content. The owner FK cascades on account deletion;
owner/submission uniqueness prevents old submissions from being re-admitted. The
cleanup transaction creates a receipt before deleting a run. A completed marker
keeps valid chat context selectable after its detailed journal has expired. Downgrade
refuses while receipts remain, preserving replay barriers. This migration has been
applied only to disposable test data; it is unapplied to the running application.

AiRepository exposes domain records without ORM/framework types. Its SQLAlchemy
implementation joins the caller's transaction; it does not commit or open a model
connection. Message insertion atomically advances the expected conversation sequence.
Only user messages update last_user_message_at. Run changes check prior state and
version, preventing stale running/interrupted/running writes. Attempt/tool completion
can replace only a started record. A caller must roll back on failure.

Database constraints protect unique submissions and active runs. The API lifecycle
adds transactional admission, duplicate-payload checks and middleware attempt/tool
records. A row or checkpoint is not proof of a committed business action.

OwnedPostgresSaver binds one user and conversation and rejects other thread IDs,
unscoped listing and inherited destructive/copy operations. Every storage cursor
checks the active user and a nonexpired conversation under shared row locks in the
same short transaction as its checkpoint access. This prevents a concurrent deletion
from leaving newly committed orphan checkpoints. Native tests verify that a concurrent
deletion waits for the guarded transaction, then cascades its committed state.
The caller supplies an autocommit Psycopg connection with no outer transaction and
owns its lifetime. Model/tool execution does not hold a storage transaction open;
LangGraph may persist checkpoints independently in the background. The serializer
disables pickle fallback and arbitrary MessagePack module loading.

The API also binds the saver to a running execution. Every batch rechecks that run;
cancellation and the 60-second admission deadline prevent further checkpoint writes.
Overdue-run reconciliation closes uncertain work without replay; see
[execution/recovery](ai-api.md#execution-deadlines-and-recovery). Server-issued ukladen_run_id metadata
links checkpoint branches to run records. New work loads its current checkpoint or
the latest completed predecessor, excluding unfinished failed/cancelled branches.

The factory owned_offline_runner validates the checkpoint migration register and
returns the existing fake runner through AgentRunner. It issues no DDL and opens no
connection. The LLM receives neither database credentials nor these repositories.

## Content, deletion and retention boundaries

Messages and checkpoints are conversation content. Deleting the conversation
cascades both. Runs survive with conversation_id cleared; attempts/tool outcomes
remain attached to their run. Owner-wide submission uniqueness therefore survives
chat deletion; minimal run receipts preserve it after the execution journal is independently purged. User-account
deletion cascades the journal too. The API deletion endpoint also cancels active work
and marks unfinished journal entries interrupted before deleting conversation content.

The execution journal stores no prompts, titles, tool arguments/results, raw errors,
provider payloads or API secrets. Error categories are fixed. Missing token usage is
NULL, independently for input/output; a measured zero is stored as zero. A request
digest supports payload comparison; it is not a prompt copy or a stored authorization.

Checkpoint access expires exactly 30 days after the last user message, using creation
time for an empty conversation. Reads and assistant/tool activity do not renew it.
Repository reads alone do not enforce expiry; the application lifecycle checks it
before admission/history and filters lists in SQL. Bounded worker cleanup cancels
pending work and physically deletes expired conversation content. Detailed journal
records expire independently on their last execution transition (terminal run finish;
attempt/tool outcome, or start if unknown). No read renews retention. Run receipts
preserve only replay/committed-context markers until account deletion; see the
[exact cleanup and visibility contract](ai-api.md#physical-retention-and-replay-protection).
The existing pure harness does not enforce owner/expiry without this owned adapter.

## Verification boundary

Offline tests cover domain transitions/usage, repository owner and concurrency
predicates, compiled PostgreSQL DDL, static migration SQL and mocked guarded cursors.
They open no database connection.

[Native persistence tests](../../apps/backend/tests/test_ai_persistence.py) use
AI_TEST_DATABASE_URL as an explicit disposable target, independently of app settings.
Each test creates and finally drops its own random schema; committed data is visible
to independent checkpoint connections/processes. With the target unset these tests
skip. Set AUTH_TEST_DATABASE_URL to the same disposable target to also run the existing
full migration round-trip/metadata test. From apps/backend:

~~~bash
uv run pytest tests/test_ai_persistence.py tests/test_auth_persistence.py -q
~~~

Native tests cover upgrade/downgrade/metadata, preserved existing users, populated
downgrade refusal, foreign ownership, uniqueness/bounds, rollback, version conflicts,
concurrent message/run admission, guarded deletion, content/journal cascades and
expiry at exactly 30 days. The fresh-process driver uses only FakeChatModel: approval
executes the synthetic tool once, rejection never executes it, stale reviews fail,
and foreign/deleted conversations cannot resume. No live provider is invoked.
See the dated execution record for environment, results and cleanup. The API and
accounting hooks add native HTTP tests. Step 7 additionally tests process termination
during an actual fake-model dispatch, fresh-process reconciliation, deadline/cancel
races, rollback/concurrent sweeps and durable budgets across reviewed resumes.
Step 8 adds native expiry/purge, independently timed journals, minimal receipts,
preserved completed context, rollback, owner isolation, bounded/concurrent cleanup
and late-result non-resurrection tests.
