# AI Setup and Provider Switching Runbook

Updated: 2026-10-22.
Status: the internal offline harness is implemented; AI-01 step 4 prepares owned
persistence adapters and an unapplied migration. Native persistence validation and
later setup instructions remain planned. AI routes/settings, credentials, real model
adapters and embedding workers do not exist. Proposed environment settings
do not enable an AI feature in today's app. No provider request or deployment was made.

Use [product scope](../product/ai.md), [stages](ai-implementation-plan.md),
[contracts](ai-tool-contracts.md) and [ADR 0009](../adr/0009-specify-provider-neutral-ai-orchestration.md).
LLM, embeddings and web search have independent adapters. The operator may offer
several supported models and users may connect personal supported API accounts.
DeepSeek/GLM are owner examples, not verified endpoints/model identifiers. No default
provider, current price or universal OpenAI-compatible contract is assumed.

## A. AI-00/01: stay offline first

1. Use the agreed specification, fixture and existing [local guide](local-development.md)
   or [home profile](../deployment/home-server.md). Preserve working env files,
   credentials and volumes. Ordinary CI uses fake providers and synthetic content.
2. Follow the [owner-approved step workflow](ai-01-execution-plan.md). Prove LangChain
   create_agent, HITL middleware and LangGraph/PostgreSQL checkpointer compatibility
   with the repository Python 3.14/runtime before adding dependencies. Reuse these
   mechanisms; keep framework types out of domain/application contracts.
3. Implement AI-01 with preserving Alembic migrations, including checkpoint schema,
   and disposable PostgreSQL/Redis. Do not run automatic schema setup on API startup.
   Verify conversation ownership, checkpoints, cancellation/restart, attempts/unknown
   usage, duplicate submission and complete content cleanup before real integration.
4. Only after AI-01 implements the settings, its proposed offline configuration is:

~~~dotenv
AI_ENABLED=true
AI_LLM_PROVIDER=fake
AI_LLM_MODEL=fake-v1
AI_EMBEDDING_PROVIDER=disabled
AI_ENABLED_CAPABILITIES='[]'
AI_AUTOMATIC_ACTIONS_ENABLED=false
~~~

Validate the existing base stack without printing expanded secrets:

~~~bash
docker compose config --quiet
~~~

For home configuration use the deployment guide's home_compose helper and its quiet
config check. These checks do not implement or enable AI. Fake/non-AI installations
must not require a new secret file or access to model networks.

### A1. Implemented offline harness

`ai.application.agent` defines framework-neutral Pydantic input/result/review DTOs
and the AgentRunner protocol. `ai.infrastructure.agent.OfflineAgentRunner` composes
create_agent with built-in model/tool limits, ToolErrorMiddleware and HITL; it does
not implement a second model/tool loop. `integrations.llm.fake.FakeChatModel` supplies
scripted responses based on checkpointed messages rather than a mutable response index.
`ai.infrastructure.fake_tools` contains pure bounded integer tools only.

Run the network-free harness tests from `apps/backend`:

~~~bash
uv sync --frozen
uv run pytest tests/test_ai_agent.py -q
~~~

The caller injects a checkpointer explicitly; unit tests use strict MessagePack
serialization and InMemorySaver. In-memory checkpoints disappear with the process.
The separate step-2 PostgreSQL proof does not verify the step-4 owned adapter.
No API/startup/worker imports or registers this harness; conversation IDs are internal
identifiers, not an implemented ownership check or a public execution endpoint.

Messages are limited to 16 KiB UTF-8; model/tool call limits are at most 4/8 per
framework invocation. Tool errors/results and review batches are sanitized/bounded.
Only approve/reject are accepted, matched to the current interrupt and ordered batch;
new messages cannot skip an unfinished execution. Changed arguments require another
proposal in the future business review flow. The harness suppresses LangSmith tracing
per invocation even if ambient tracing environment flags are enabled. Fake responses
do not fabricate token usage or require API keys.

Direct framework pins are LangChain 1.4.7, langchain-core 1.6.13, LangGraph 1.2.16,
langgraph-checkpoint 4.3.0, langgraph-checkpoint-postgres 3.2.0 and LangSmith 0.14.12.
The core/checkpoint packages are directly imported framework APIs; the PostgreSQL
package is used by the prepared owned adapter. LangSmith is already transitive and directly imported
only to disable remote tracing. The tested Linux environment gains 26 runtime
distributions; the universal lock also contains a platform-specific SDK dependency.
The required websockets downgrade is 17.1 to 16.1.1; other existing pins are preserved.
These dependencies replace custom loop/review/persistence machinery, but add framework,
serialization, transport and checkpoint-schema maintenance. No LangSmith account,
tracing service, separate agent server or provider SDK is activated.

Durable attempt budgets across retry/resume, concurrent admission, authentication,
cancellation, retention and business authorization are not implemented by this harness.
Its built-in per-invocation limits cannot substitute for the planned durable ledger.

Verification (2026-10-22): 26 offline harness tests; full backend pytest 988 passed /
553 native-service checks skipped with PostgreSQL/Redis/S3 targets unset; full
Ruff/format/Pyright, dependency/lock and quiet Compose checks passed. See
[the execution record](ai-01-execution-plan.md#12-delivery-progress-2026-10-22).

### A2. Prepared owned persistence

The domain state, AiRepository port, SQLAlchemy adapter and OwnedPostgresSaver are
implemented internally. Revision 0022_ai_persistence prepares application and pinned
checkpoint tables; it has not been applied or validated against native PostgreSQL.
No startup code calls framework setup or enables the feature. See
[the schema, transaction and deletion contracts](ai-persistence.md).

owned_offline_runner composes the existing fake harness with an owner-bound saver.
Its caller supplies and closes a Psycopg connection with autocommit enabled and no
outer transaction. Each checkpoint operation checks ownership/expiry inside a short
transaction; no storage transaction encloses a model call. Application repositories
participate in caller-owned SQLAlchemy transactions. There is no public API or durable
attempt/tool recording hook yet. This internal composition is not an activation recipe.

Run the offline storage checks with no service targets configured:

~~~bash
uv run pytest tests/test_ai_agent.py tests/test_ai_state.py tests/test_ai_checkpoint_storage.py -q
~~~

Tests compile the migration and check state/filter/cursor behavior using mocks. Native
migration, concurrency, rollback and process-restart verification require separately
approved step 5. Retention cleanup and deletion endpoints remain step 8/6 work.

## B. AI-02: verify one supported adapter before activation

1. Choose an operator-supported provider, exact model and credential source. Verify
   official request/response/tool/streaming/structured-output contracts and account
   model access at implementation time. Never invent DeepSeek/GLM model IDs or assume
   another provider's wire format is identical.
2. Record feature profile, account/organization quotas, timeout/retry behavior, data
   processing/retention terms, prices if known and configured request/token/budget
   admission. Free offerings still have quotas; missing price/usage is unknown.
3. Implement/test the normalized adapter behind LlmProvider. Explicitly reject modes
   it cannot support; use separate validated steps when its structured/tool/streaming
   features cannot be combined. No implicit fallback to another provider or payer.
4. Perform one intentionally activated synthetic application smoke, recording actual
   attempts/usage and safe outcomes. Simulate 429/timeouts/refusals in fake tests;
   do not cause unnecessary real rate-limit requests. Private files are not probes.
5. Activate real source processing only after ownership, secret handling, feature
   profile and admission tests pass. AI use provides the product data-processing
   agreement; there is no extra confirmation dialog for each source read. The UI
   identifies the selected connection/provider and relevant source scope.

No vendor setup command is authoritative until the corresponding adapter is delivered.
Connection validation itself is a bounded external request and must be explicitly
initiated by the account owner/operator, not automatically run during app startup.

### Operator offerings

Add a versioned supported connection/model entry and configure its secret only for
processes that actually dispatch through it. Existing shared env-file anchors must
not distribute LLM/search secrets to extraction, migration or unrelated workers.
A private optional secret file can be introduced with tested ignore/loading rules;
verify it is ignored before creation. Never print resolved secret configuration.

The catalog exposes safe model/provider/capability metadata, never operator keys.
Multiple offerings do not require multiple agents or model routing heuristics.
Catalog changes do not retroactively change a pending action's authorization.

### Personal API connections

Implement authenticated/CSRF-protected add, masked metadata/list, choose and disconnect.
Persist encrypted owner-only credentials server-side with a deployment-managed master
key outside PostgreSQL; never put plaintext keys into prompts/checkpoints/logs or GET
responses. Test encryption failure, rotation, account isolation and backup handling.
Do not accept arbitrary user-provided base URLs to internal networks.

Disconnect immediately prevents new/queued dispatch via that connection; do not retry
using another user's or the operator's key. Explain incomplete/in-flight outcomes
honestly. Using a personal free model does not grant unlimited application quotas.
The API process and any future generation worker need explicitly scoped access;
embedding/extraction workers do not inherit unrelated credentials.

## C. AI-03/04: tools, chats, instructions and usage

Register only delivered application capabilities. Start with calendar/search/page
reads; material text needs the new bounded excerpt contract, not original-byte download.
Use synthetic cases first. Actual source reads must revalidate ownership/trash/version
before each context build, including old tool results and source-derived summaries.

Deliver planned /workspace/ai and /workspace/ai/usage with separate chats, streaming,
cancellation/reconnect, source viewer, model/BYOK settings and personal instructions.
The instruction field guides responses; it never grants tools or bypasses confirmation.
Verify logout/session change discards all private state and masks every credential.

Test 7/30-day owner-only usage, known vs unknown tokens, attempt/run arithmetic and
price snapshots. Chats expire 30 days after last user message; merely viewing them
or running a background job does not renew retention. Content-free activity expires
30 days from each event. Manual deletion/expiry covers historical checkpoints and
chat-derived context, preserving created business objects and minimal replay protection.

## D. AI-05/06: prove embeddings, then build the index

1. Local CPU E5-small is a candidate from the earlier plan, not a mandatory LLM
   dependency. Prove Python 3.14 CPU packages and container compatibility before
   selecting/pinning a model runtime. No silent Python downgrade or CUDA install.
2. Record model/tokenizer revision, dimensions, normalization and document/query
   prefixes from official sources. Bound tokens with the real tokenizer.
3. Measure combined API query-model and indexing-worker copies under full-stack
   load, cold/warm latency, throughput, RSS/swap and unrelated API responsiveness.
   Two separate processes have two model copies; normal workers load neither.
4. If local inference is unsuitable, select a supported API embedding adapter with
   its own privacy/price/quota gate. No silent remote transfer for indexing.
5. Deliver preserving chunk/index migrations, fenced/recoverable jobs and dedicated
   bounded queue/worker wiring in local/home profiles. These workers do not exist yet.
6. Fuse lexical/vector results, track full-source coverage and keep lexical mode
   available on semantic failure. Test edits/trash/access loss before cleanup runs.
7. Model/dimension changes require a new generation/rebuild, quality checks and
   explicit activation. Preserve canonical sources and previous valid generation.

Do not add a serving microservice, reranker or ANN index without measured need.
Record executed hardware results rather than claiming a target was met.

## E. AI-07/08: confirmed writes and scoped automatic creates

Enable each write capability only after normal-service previews, version checks,
exact confirmation, transaction/idempotency and lost-response tests pass. Start on
disposable data. Requested note edits preserve block IDs/schema and source versions.
All-or-nothing multi-action application requires an actual shared transaction and
availability serialization; checkpoints alone cannot provide it.

Automatic dispatch stays off until AI-08 and a real owner grant exist. Initial
allowlist: new-page/new-task creation in selected scopes; tasks require AI-10.
Each grant specifies operation, targets, parameter/count limits, expiry and trigger.
Moves/edits/deletes remain confirmed operations. Test revocation against queued work.

## F. P-06/AI-10: task planning

Deliver typed tasks, explicit source links/subtasks/dependencies, task sessions,
calendar occupied/free/conflict interfaces and structured work preferences first.
Ask for allowed work windows; use editable 45/15-minute session/break defaults.
Label unknown effort estimates and preserve source/uncertainty information.

Planner computation is deterministic. General replanning protects personal appointments
and official events and moves eligible task sessions only. Stale/missing official
coverage permits a conditional preview, not application of affected changes. Recheck
freshness, complete busy set, task/preferences versions and conflicts before a single
atomic plan commit. Any changed precondition requires a new preview/confirmation.

## G. AI-11/12: fallback and proactive reviews

Use an explicitly supported web-search adapter, not unrestricted HTTP or hosted code.
For workspace questions retrieve local sources first, disclose insufficiency and
label general knowledge/public citations. Bound/minimize external queries and treat
results as untrusted. No API key/private note dumps, internal URL access or invented
private deadlines/completion. Unavailable retrieval is not a confirmed no-match.

Proactive reviews start disabled. User-selected schedules/frequency feed existing
Celery/Beat/in-app delivery; no external notification channel is implicitly selected.
Deduplicate and skip unchanged/non-actionable work. Recheck settings/connection/grants
when queued work executes. A briefing cannot grant automatic writes.

## H. Switch, disable and recover

| Change / failure | Required response |
| --- | --- |
| Switch offered/personal LLM | Explicit supported connection/model choice, feature validation and fixed-fixture evals; never implicit billing fallback |
| Add another API | Implement/test its adapter and credential/price/data contract; preserve tools/domain semantics |
| Change embedding model | New validated index generation; never mix incompatible query/document spaces |
| 401/403 or disconnect | Safe unavailable-connection status, stop new dispatch and preserve honest attempt outcomes |
| 429 or provider timeout | Bounded retry/admission; no infinite wait or alternate key |
| Missing/truncated usage | Unknown/incomplete accounting; no fabricated zero or automatic replay of writes |
| Memory/CPU pressure | Count model copies, reduce threads/batch/concurrency or pause indexing; preserve sources |
| Dashboard vs vendor console | Other traffic/shared keys, unknown usage and reporting windows; app totals are not invoices |
| Disable AI/capability/grant | Stop future dispatch/pending execution as applicable; preserve committed objects/outcomes |

## I. Handoff and historical context

For each delivered stage record: local commit, implemented settings/routes, exact
local/home commands, checks, adapter/model revisions, real-call count, usage completeness,
hardware results, rollback and remaining activation gates. Push/deployment require a request.

The 2026-10-17 plan used Groq Free/GPT-OSS and CPU E5-small examples. It did not execute
provider probes or prove packages/hardware. Its dated documentation verification is
preserved in [the plan](ai-implementation-plan.md#18-historical-planning-document-verification-2026-10-17).
That historical baseline does not constrain today's operator/BYOK model selection.
