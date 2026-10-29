# AI Setup and Provider Switching Runbook

Updated: 2026-10-29.
Status: AI-01 is complete within its offline scope: harness, owned persistence,
authenticated fake API, durable accounting, bounded recovery and retention cleanup.
Disabled by default; migrations are tested on disposable data and unapplied to the
running application. See [final verification](ai-01-execution-plan.md#13-final-ai-01-verification-2026-10-24).
AI-02 adds optional [OpenRouter models and encrypted credentials](ai-connections.md),
implemented locally but unactivated. [AI-03 source reads](ai-03.md) are implemented
locally. [AI-04](ai-04.md) adds locally implemented streaming chat, source viewing,
preferences and usage UI/API. [AI-05](ai-05.md) adds optional local CPU embeddings and
a disposable proof worker. [AI-06](ai-06.md) adds locally implemented versioned
index jobs, hybrid retrieval and durable complete-source processing; activation
remains pending. AI-07 implements local confirmed actions; AI-08 is deferred indefinitely.
[AI-09 local hardening](ai-09.md) is verified; live quality and activation remain pending.
See [current API and recovery limits](ai-api.md). No provider request or deployment was made.

Use [product scope](../product/ai.md), [stages](ai-implementation-plan.md),
[contracts](ai-tool-contracts.md) and [ADR 0009](../adr/0009-specify-provider-neutral-ai-orchestration.md).
LLM, embeddings and [web search](ai-11.md) have separate implemented adapter boundaries;
web search remains default-disabled and unactivated. The operator may offer
several supported models and users may connect personal supported API accounts.
AI-02 verifies the OpenRouter contract for the owner-selected DeepSeek V4.1 Flash
profile and an optional free example; live account behavior remains unverified.
GLM and other adapters are future choices. No universal wire contract or current
account price is assumed.

The 2026-10-25 [catalog/access follow-up](ai-connections.md#application-key-and-developer-managed-models)
makes the shared application connection the normal path: the provisioning template
selects public DeepSeek V4.1 Flash 1017, while Claude Haiku/Sonnet and GPT-5.5 are
listed but disabled. Users need no personal key. Free/unlimited product access and
owned usage accounting are implemented; subscription/quota persistence remains future
work. Runtime AI flags still default to false; no model/account has been activated.

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
4. The implemented offline settings are below. Both flags default to false. These
   opt-in values require the reviewed current Alembic head, including 0025,
   to be applied to the target first;
   enabling them gives fixed synthetic answers, with no source access or real model:

~~~dotenv
AI_ENABLED=true
AI_RETENTION_ENABLED=true
AI_LLM_PROVIDER=fake
AI_LLM_MODEL=fake-v1
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
The [API composition](ai-api.md) supplies authenticated admission, owned checkpoints
and accounting. Direct harness construction still treats conversation IDs as internal
identifiers and does not itself authenticate a caller. Execution stays in the request;
only recovery and retention maintenance are scheduled on the existing worker.

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
package is used by the owned adapter. LangSmith is already transitive and directly
imported only to disable remote tracing. The tested Linux environment gains 26 runtime
distributions; the universal lock also contains a platform-specific SDK dependency.
The required websockets downgrade is 17.1 to 16.1.1; other existing pins are preserved.
These dependencies replace custom loop/review/persistence machinery, but add framework,
serialization, transport and checkpoint-schema maintenance. No LangSmith account,
tracing service, separate agent server or provider SDK is activated.

The pure harness does not implement admission or authorization. The owned API adds
authentication, per-run durable budgets, concurrent admission and cancellation through
middleware/services. Step 7 adds bounded ConnectionError retries, execution deadlines
and conservative crash reconciliation; see [their exact limits](ai-api.md#execution-deadlines-and-recovery).
Step 8 adds physical retention and minimal replay/context receipts. Business
authorization remains later work; built-in per-invocation limits do not replace the journal.

Verification (2026-10-22): 26 offline harness tests; full backend pytest 988 passed /
553 native-service checks skipped with PostgreSQL/Redis/S3 targets unset; full
Ruff/format/Pyright, dependency/lock and quiet Compose checks passed. See
[the execution record](ai-01-execution-plan.md#12-delivery-progress-2026-10-22).

### A2. Internal owned persistence

The domain state, AiRepository port, SQLAlchemy adapter and OwnedPostgresSaver are
implemented internally. Revision 0022_ai_persistence prepares application and pinned
checkpoint tables; native migrations and ownership/restart checks passed only on
disposable PostgreSQL, with no application database migration.
No startup code calls framework setup; the feature defaults off. See
[the schema, transaction and deletion contracts](ai-persistence.md).

owned_offline_runner composes the existing fake harness with an owner-bound saver.
Its caller supplies and closes a Psycopg connection with autocommit enabled and no
outer transaction. Each checkpoint operation checks ownership/expiry inside a short
transaction; no storage transaction encloses a model call. Application repositories
participate in caller-owned SQLAlchemy transactions. Direct harness construction
does not supply authenticated admission or attempt/tool accounting. The API adds that lifecycle
and reuses this storage composition; see its separate contract.

Revision 0023_ai_run_receipts adds minimal replay/context markers before detailed
journals are purged. Both revisions are tested only on disposable schemas and remain
unapplied to the running app. Keep AI_RETENTION_ENABLED=true in worker/Beat after an
approved activation, even when chat is later disabled; both flags false intentionally
perform no AI SQL on an unmigrated installation. No new queue/service is introduced.

Run the offline storage checks with no service targets configured:

~~~bash
uv run pytest tests/test_ai_agent.py tests/test_ai_state.py tests/test_ai_checkpoint_storage.py -q
~~~

These tests compile the migration and check state/filter/cursor behavior using mocks.
Step-5 native tests additionally verify migrations/metadata, owner constraints,
concurrent admission/deletion, rollback and approve/reject resume in fresh interpreters;
see the persistence guide for their explicit test target. Step 6 adds chat/run transport,
manual deletion, cancellation, idempotency and attempt/tool hooks. Step 8 implements
bounded physical cleanup and replay markers. Step 7 adds deadlines/retry accounting
and the ai.reconcile_runs task, extended with retention in step 8;
enable AI_ENABLED/AI_RETENTION_ENABLED in the relevant consumers only after an explicitly
approved migration/activation. No new queue, service or dependency is needed.

## B. AI-02: verify one supported adapter before activation

The [implemented OpenRouter setup](ai-connections.md) now defines the catalog,
AI-consumer secret mounts, encrypted personal connections, immutable chat selections
and offline/native tests. Live account smoke and application activation remain pending.
Keep real keys and configured catalogs under ignored .secrets/ai/, never in shared env files.

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
4. Obtain the owner's explicit bounded real-request approval under
   [the spending policy](../../AGENTS.md#owner-approval-for-real-api-usage) before
   any real smoke, independently of key provisioning or activation. Perform only
   the approved synthetic application smoke, recording actual
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
honestly. Product access currently has no user quotas; provider/account rate limits
still apply independently.
The API process and optional AI document worker have explicit consumer-only mounts;
embedding/extraction workers do not inherit unrelated credentials.

## C. AI-03/04: tools, chats, instructions and usage

AI-03 now registers the [delivered source tools](ai-03.md) on tool-capable offerings:
calendar/search/page/material/database reads through normal application services.
The bounded excerpt contract reads extracted text without original-byte downloads.
Synthetic tests verify source reconstruction, owner/trash/version checks and suppression
of stale tool bodies/source-derived summaries. Review the 0025 migration and whole-request
input budget before activation; no real-model request has been made.

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

AI-05 is delivered through the [CPU runtime/proof guide](ai-05.md). Its pinned ONNX
candidate meets the initial targets at the documented bounded load, not continuous
saturation. Steps 5–7 are implemented locally in [AI-06](ai-06.md); application activation
remains pending. The optional `embeddings` consumer and `ai` document consumer
profiles preserve other workers. Combine `docker-compose.retrieval.yml` for CPU
retrieval with the AI catalog overlay only after separate activation approval.

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

AI-07 is implemented locally, default-disabled and unactivated; see [contracts](ai-07.md).
`AI_ACTIONS_ENABLED=false` remains the default. Migrate reviewed revision 0031 before
separately requested activation. Enabling confirmed actions never grants automatic writes.

Enable each write capability only after normal-service previews, version checks,
exact confirmation, transaction/idempotency and lost-response tests pass. Start on
disposable data. Requested note edits preserve block IDs/schema and source versions.
All-or-nothing multi-action application requires an actual shared transaction and
availability serialization; checkpoints alone cannot provide it.

AI-08 is deferred indefinitely by the owner (2026-10-26). Current business-content
writes always require exact confirmation. The following is future reference only:
automatic dispatch would require a new owner decision, AI-08 and a real grant. Initial
allowlist: new-page/new-task creation in selected scopes; tasks require AI-10.
Each grant specifies operation, targets, parameter/count limits, expiry and trigger.
Moves/edits/deletes remain confirmed operations. Test revocation against queued work.

## F. P-06/AI-10: task planning

Implemented locally with browser controls under [AI-10](ai-10.md);
[task planning](task-planning.md) records actual endpoints, bounds and verification.
Activation and real-provider quality remain separate gates.

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

AI-11 is implemented locally under the [bounded search contract](ai-11.md). The
per-offering `web_search` flag defaults to false; activation/spending needs separate
authorization. [AI-12](ai-12.md) implements opt-in reviews locally; its background
runtime is default-disabled and unactivated. No new per-search UI step is required.

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
