# AI Persistence Contracts

Updated: 2026-10-22.
Status: AI-01 steps 4/5 implement and natively test internal owned persistence.
The migration has been applied only to disposable test schemas, never to the app.
No HTTP/worker path uses this storage yet. Read the
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

AiRepository exposes domain records without ORM/framework types. Its SQLAlchemy
implementation joins the caller's transaction; it does not commit or open a model
connection. Message insertion atomically advances the expected conversation sequence.
Only user messages update last_user_message_at. Run changes check prior state and
version, preventing stale running/interrupted/running writes. Attempt/tool completion
can replace only a started record. A caller must roll back on failure.

Database constraints protect unique submissions and active runs. Request admission,
duplicate-payload handling and automatic attempt/tool recording are not implemented
until the lifecycle step. A row or checkpoint is not proof of a committed business action.

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

The factory owned_offline_runner validates the checkpoint migration register and
returns the existing fake runner through AgentRunner. It issues no DDL and opens no
connection. The LLM receives neither database credentials nor these repositories.

## Content, deletion and retention boundaries

Messages and checkpoints are conversation content. Deleting the conversation
cascades both. Runs survive with conversation_id cleared; attempts/tool outcomes
remain attached to their run. Owner-wide submission uniqueness therefore survives
chat deletion until the execution journal is independently purged. User-account
deletion cascades the journal too. These are schema rules, not implemented endpoints.

The execution journal stores no prompts, titles, tool arguments/results, raw errors,
provider payloads or API secrets. Error categories are fixed. Missing token usage is
NULL, independently for input/output; a measured zero is stored as zero. A request
digest supports payload comparison; it is not a prompt copy or a stored authorization.

Checkpoint access expires exactly 30 days after the last user message, using creation
time for an empty conversation. Reads and assistant/tool activity do not renew it.
Repository reads alone do not enforce expiry; the future application lifecycle must
check it before admitting work or returning content. Physical content cleanup,
30-day journal purge, cancellation and deletion endpoints remain unimplemented.
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
See the dated execution record for environment, results and cleanup. API lifecycle,
durable accounting hooks, crash reconciliation and retention jobs remain later work.
