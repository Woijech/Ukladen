# AI Implementation Plan

Updated: 2026-10-17.
Status: planned; **every AI-00 through AI-09 stage below is not implemented**.
This request authorizes documenting the plan, not executing its implementation,
creating accounts, sending content to providers, deploying or enabling automatic writes.

Read [system architecture](../../SYSTEM_ARCHITECTURE.md), [AI architecture](../architecture/ai.md),
[ADR 0005](../adr/0005-support-scoped-ai-action-permissions.md),
[the scenario/analytics specification](../product/ai.md) and
[setup instructions](ai-setup.md). P-09 in [the roadmap](implementation-roadmap.md)
remains not implemented. This plan does not start P-06 tasks/availability.

## 1. Delivery map and connection gates

| Stage | Deliverable | Connect at this stage | Exit evidence |
| --- | --- | --- | --- |
| AI-00 | Scope, data policy, configuration contract, fixture scenarios | Nothing external | Decisions and acceptance cases are explicit |
| AI-01 | Provider ports, fake orchestration, durable runs and usage ledger | Existing PostgreSQL/Redis only | Offline HTTP/service/persistence checks |
| AI-02 | Groq adapter, admission limits and one synthetic smoke run | Groq Free key, API process only | Actual account quota, one recorded bounded call |
| AI-03 | Authorized read tools and lexical grounding | Existing calendar/notes/search services | Ownership, freshness, bounded source and injection cases |
| AI-04 | Chat, source viewer and owner usage page | Frontend to existing same-origin API | Desktop/mobile browser checks and analytics arithmetic |
| AI-05 | CPU embedding dependency/hardware proof | Download pinned E5-small weights; no new cloud account | Python 3.14 compatibility and full-stack memory/latency report |
| AI-06 | Versioned chunks, embeddings and hybrid retrieval | pgvector tables and embedding queue | Index lifecycle, retrieval quality and restart recovery |
| AI-07 | Exact confirmed creates | Existing page/event/reminder services | Version/idempotency/commit and confirmation regressions |
| AI-08 | Optional scoped automatic actions | Only a separately specified grant and trigger | Revocation/limits/queued-job tests |
| AI-09 | Release hardening and replacement rehearsal | Same-model test choice; optional second adapter | Evaluations, failure recovery, backups and owner acceptance |

AI-00 -> AI-01 -> AI-02 -> AI-03 -> AI-04 is the first useful release.
AI-05/06 add semantic retrieval; they do not block lexical assistance. AI-07 depends
on AI-01 through AI-04, not on embeddings for calendar-only creates. AI-08 is optional
and must not hold up the confirmed-action release. Hardware investigation can run
earlier after AI-00 if explicitly included in an implementation request.

Each stage is a cohesive implementation request/commit. Stop after its acceptance
report; do not advance into the next project phase without a request. Stages have
completion criteria rather than unmeasured calendar-date promises.

## 2. Existing components and places the change must reach

| Area | Reuse / planned responsibility |
| --- | --- |
| `modules/ai` | Currently a marker; add conversation/run/action orchestration, policy and usage read services |
| `integrations/llm` | Currently a marker; add the Groq SDK adapter, then later providers only as needed |
| `integrations/embeddings` | Currently a marker; add local CPU model loading, tokenization and embedding adapter |
| `modules/search` | Existing authorized lexical search; own derived chunks, embedding jobs and hybrid retrieval |
| Calendar/notes/relations/workspace/reminders | Reuse application interfaces, versions and transaction ownership; never call route handlers internally |
| `core/config.py`, `main.py` | Validate staged settings and install AI transport/dependencies without provider SDK types leaking into domain |
| Alembic metadata/migrations | Real constraints, owner indexes, migration preservation and derived-index rebuild behavior |
| Celery registration / Compose / home overlay | Add indexing jobs after AI-05, preserve material/email/reminder queues and home exposure rules |
| Backend dependency lock / CI | Groq SDK first; embedding packages only after the Python 3.14 wheel check |
| Web workspace/auth/query scope | Reuse identity isolation, expiry/registration handling, source viewer and A1 branding |
| `.env.example`, home example, private AI env ignore | Add supported settings only with their stage; no real secrets in Git |
| Backend/browser tests and docs | Fixtures, failure cases, actual API documentation, per-stage capability status |

The current material download API returns original bytes, while lexical search
returns bounded snippets. A full extracted-text/excerpt application read capability
is a new AI-03/06 dependency, not an already available unrestricted tool.

## 3. Proposed configuration, not current application settings

| Setting | Planned default / stage |
| --- | --- |
| `AI_ENABLED` | `false`; fail closed / AI-01 |
| `AI_LLM_PROVIDER` | `fake`; `groq` is an explicit AI-02 activation |
| `AI_LLM_MODEL` | `openai/gpt-oss-120b` for Groq; `openai/gpt-oss-20b` is a manual test choice |
| `GROQ_API_KEY` | Unset; private API-process secret / AI-02 |
| `AI_ENABLED_CAPABILITIES` | Empty allowlist; add only delivered capabilities from the product catalog |
| `AI_EMBEDDING_PROVIDER` | `disabled`; change to `local` after AI-05/06 |
| `AI_EMBEDDING_MODEL` | `intfloat/multilingual-e5-small`; pin the resolved model revision before indexing |
| `AI_EMBEDDING_DEVICE` | `cpu`; reject unsupported values / AI-05 |
| `AI_EMBEDDING_THREADS` | `2` / AI-05 |
| `AI_EMBEDDING_BATCH_SIZE` | `4` initially; tune from measurements / AI-05 |
| `AI_AUTOMATIC_ACTIONS_ENABLED` | `false`; requires AI-08, not merely a nonempty allowlist |

Use typed settings and a small explicit composition function. Do not build a dynamic
provider plugin system or persist SDK objects. No configuration flag guarantees a
zero bill after an operator upgrades the provider account; keep Groq Free and paid
fallback absent. Changes to paid account policy require a separate decision.

## 4. AI-00: freeze the small first slice

**Deliver:** a selected subset of [scenario IDs](../product/ai.md#2-editable-scenario-catalog),
synthetic fixtures, prompt/version identifiers, enabled-capability mapping and data policy.

1. Select AI-UC-01/02/03/14 first; leave optional scenarios unadvertised.
2. Record Groq Free, 120B baseline and local E5-small as development targets.
3. Decide which source scopes can leave the server. Until recorded, use synthetic
   content only. Document that local embeddings do not keep later LLM excerpts local.
4. Resolve prototype retention, chat deletion and audit/idempotency retention before
   their first private-data or write stage. Product defaults are reviewable choices.
5. Define bounded input/tool/output/iteration budgets and one active run per conversation.
   Set initial values below actual account limits, then adjust from measurements.
6. Prepare about 30 synthetic acceptance cases: dates/DST, no academic profile,
   stale IIS, missing sources, foreign IDs, embedded malicious instructions and timeouts.

**Connect:** nothing. No API key is needed to write contracts or run fake tests.
**Done:** the selected use cases, data policy and expected outcomes are explicit.
**Stop/rollback:** keep AI disabled; existing product behavior is unchanged.

## 5. AI-01: offline runtime and accounting first

**Deliver:** `LlmProvider`, `EmbeddingProvider`, normalized request/result types,
a deterministic fake, owner-scoped conversations/messages/runs and durable usage records.
Own `LlmProvider` in `ai.application` and `EmbeddingProvider` in `search.application`;
integration adapters implement those ports. Retrieval must not depend on AI orchestration.
Separate `embed_query` and `embed_documents`; the adapter owns E5 prefixes and limits.
Normalize text/tool requests, call IDs, finish/refusal/error state and usage. Preserve
provider continuation metadata privately when needed; never erase required call state.

Suggested records, finalized by migrations in this stage:

| Record | Minimum responsibility |
| --- | --- |
| Conversation/message | Owner, ordered messages, selected source scope, timestamps and deletion/retention |
| Run | Owner/conversation, unique owner-scoped submission key, scenario/prompt version, state and timing |
| Provider invocation | Unique attempt ID, run, provider/model, request state, safe category, reported usage/completeness, price snapshot |
| Tool invocation | Run/call ID, tool/schema version, read/write classification, timing and safe outcome |

Keep canonical content out of the usage ledger. Do not create action/grant tables
until their executable stages need them. A run may complete with pending proposals
later; proposal execution has its own state rather than pretending the chat is still running.

Planned run states: `queued`, `running`, `completed`, `failed`, `cancelled`, `interrupted`.
Persist admission before the network call; do not hold database locks while waiting
for a model. On crash, mark unfinished work interrupted rather than automatically
replaying side effects. Each genuine retry gets a separate provider-attempt record.
Durable admission/accounting must be available before starting provider work; failure
to store a result leaves an honest incomplete attempt for recovery, never a fabricated zero.

**Transport:** planned authenticated `/api/v1/ai` conversation/message/run reads and
message submission. Use existing CSRF/Origin contracts for writes, server-derived owner,
bounded inputs, no-store responses and registration-completion/session-expiry handling.
All new routes are design targets, not existing APIs.

**Verify:** duplicate submissions, owner isolation, malformed tools, crash/retry
accounting, unknown usage, cancellation and no provider traffic in ordinary pytest.
**Connect:** disposable PostgreSQL/Redis; fake model only.
**Done:** a synthetic tool loop and usage summary are testable without an API key.

## 6. AI-02: connect Groq using synthetic content

Follow [runbook step B](ai-setup.md#b-ai-02-connect-groq-free).

1. Add/pin the official Groq Python SDK and adapt it behind `LlmProvider`.
2. Explicitly bound timeouts and retries. Prefer application-owned retries with SDK
   retries disabled so actual attempts are visible; verify the locked SDK behavior.
3. Implement per-organization/model admission using configured account limits and
   fresh provider headers. Local app usage is not global quota truth.
4. Honor `Retry-After`, bound retry count and return a retryable status rather than
   sleeping indefinitely in an HTTP request. Include cancelled/truncated/unknown usage.
5. Send only local function definitions. Hosted web, code and remote MCP tools are outside this slice.
6. Capture one synthetic request and its provider-reported usage; attach a dated smoke result.

Groq currently documents tool calls for both GPT-OSS models, but not parallel tool
calls for them. Structured Outputs currently excludes tool use and streaming.
Use schema-validated function arguments for tool turns; make a separate structured
request only where required. Treat partial tool arguments as data until complete.
Recheck these restrictions at implementation time in [tool docs](https://console.groq.com/docs/tool-use/overview)
and [structured outputs](https://console.groq.com/docs/structured-outputs).

**Done:** one synthetic end-to-end run succeeds, one rate-limit failure is handled,
the ledger distinguishes attempts from runs, and no key enters web bundles/logs.
**Rollback:** select fake/disable AI; rotate an exposed key. No provider auto-fallback.

## 7. AI-03: authorized read tools and lexical grounding

Implement only `get_calendar_events`, `search_workspace`, `read_page` and bounded
`read_material_excerpt` when its new application read contract exists. Add backlinks
or database query tools only when their optional scenarios are selected.

- Identity is injected server-side. Cross-owner UUIDs fail through normal services.
- Resolve dates using current server instant and profile timezone; preserve official
  freshness/coverage warnings. No free-time/conflict answer until P-06 exists.
- Source references carry type/ID/version and a real block/fragment location.
- Revalidate source permissions/trash/version when building each new model request;
  exclude stale/inaccessible tool bodies and source-derived assistant summaries from
  the new context. Track provenance instead of trusting an old chat summary as current data.
- Extracted material text stays search-owned and derived. Add an authorized bounded
  excerpt read through an application port; no ORM/S3 shortcut in AI.
- Treat page/file/IIS text as untrusted content. It cannot enable tools or authorize writes.
- Persist known retrieval coverage. Reject or label a requested whole-source summary
  when only a subset was read; broad document summarization remains optional.

**Verify:** source citations, safe foreign-ID errors, trash/stale/history cases,
malicious instructions, truncation and source errors distinguished from empty data.
**Connect:** existing services; embeddings remain disabled.
**Done:** AI-UC-01/02/03 work using lexical search and bounded reads.

## 8. AI-04: chat and usage page together

Implement planned `/workspace/ai` and `/workspace/ai/usage`; add a contextual calendar
entry without rewriting the calendar. Reuse/extract the existing session/query-cache
ownership boundary so logout/account changes discard every private AI view and request.
Use the approved A1 mark and Russian product text.

Start a run with an idempotent authenticated POST; stream display events with
fetch/SSE only if the stage implements cancellation and durable state recovery.
Polling an owned run is a valid first transport. Reconnecting reads stored state;
it does not resubmit a mutation or silently regenerate a costly run. Completed tool
arguments are validated before execution, regardless of streamed text.

Add a bounded read-only source drawer for current pages/material excerpts where
the product has no canonical viewer. Render stored blocks and citations as data;
no arbitrary HTML. No full editor or whole workspace navigation rebuild is required.

Planned analytics API: owner-only summary, daily series and paginated recent runs
under `/api/v1/ai/usage`; a bounded run detail endpoint rechecks ownership. Support
7/30-day presets and at most 31 civil days in the profile timezone. Return honest
unknown fields, sample counts and explicit fake/provider filters.

Implement the metric rules from [the product specification](../product/ai.md#4-usage-page):
count each provider attempt once, retain failed attempt usage, avoid reasoning/cache
double counting and keep expected free spend separate from list-price estimates.
Persist the invocation's price snapshot; do not infer an invoice from local traffic.
Model tables and daily charts can use native SVG/CSS plus accessible HTML tables;
no chart dependency or external telemetry is required for 31 daily points.

**Verify:** known fixture totals, retries, missing usage, timezone/DST grouping, zero
vs unavailable states, pagination, owner isolation, session expiry, mobile layout,
keyboard navigation and accessible chart alternatives. Optional feedback stays optional.
**Done:** the assistant and analytics work with fake fixtures and the bounded Groq smoke.
**Rollback:** disable AI navigation and dispatch; retain existing business data.

## 9. AI-05: prove CPU embeddings fit the actual host

Do this before committing the application to a heavy dependency or index schema.
The backend currently requires Python `>=3.14,<3.15`; verify compatible CPU wheels
for the chosen `sentence-transformers`/PyTorch versions, lockfile and Docker image.
Do not downgrade Python or silently install CUDA. The stack has no existing model
runtime: these dependencies solve inference/tokenization but add large wheels and RAM.
If incompatible, evaluate a supported ONNX route or the free API alternative and
record the choice before proceeding.

Pin the E5 revision, tokenizer and normalization. Enforce `query:`/`passage:` prefixes,
384 dimensions, finite values and the model's total token limit. Budget 300-400 tokens
per fragment including added context; use its tokenizer rather than character counts.

Initial process layout: one single-process API query model instance, loaded lazily,
and one single-process indexing worker using the same adapter. **These are two model
copies when both are active**; one worker does not share Python memory with the API.
Run query inference outside the async event loop with bounded concurrency. Keep CPU
packages optional/lazy so normal email/material workers do not load the model.

This layout avoids adding a model-serving microservice or queue-based request/reply
protocol. Start with two threads per instance, batch size four and one indexing task.
Measure the combined footprint, not only the worker. If it does not fit, keep semantic
retrieval off and select the documented free API adapter before changing the index.

**Hardware report:** cold/warm query p50/p95, fragment throughput, RSS per process,
full-stack memory/swap, CPU, API responsiveness and cancelled-job behavior on the
owner's powered laptop. Use synthetic texts and record CPU/OS/runtime/revision.
Initial release targets: no sustained swapping or OOM, warm query p95 <= 1 second,
and unrelated API p95 degradation <= 20% against an idle-index baseline. These are
proposed acceptance targets, not benchmark claims; report failures rather than hiding them.

**Done:** reproducible measurements and the selected local/API runtime path.
**Connect:** model download/cache only; no Groq key is needed by the embedding worker.

## 10. AI-06: versioned retrieval and indexing

Add search-owned derived chunk/embedding/job persistence through Alembic, including
owner/source/version/location, content hash, tokenizer/chunker revision, model revision,
normalization and dimensions. A 384-value vector schema is the initial choice, not
a universal storage shape for arbitrary models.

1. Obtain canonical page text and existing material extraction through application ports.
   Preserve real block IDs and available extraction offsets; do not fabricate PDF pages.
2. Split deterministically with bounded overlap and fragment count/text budgets.
3. Persist pending work with canonical writes or recoverable dirty-source scanning.
   Redis publication alone must not be the record that work is required.
4. Reuse the existing claim/execute/complete and fenced-lease pattern. Compute outside
   database transactions; publish only the still-current owner/source/index version.
5. Use a dedicated `embeddings` queue and proposed `embedding-worker`, concurrency one,
   preserving the normal and materials queues. Recover after broker/worker restart.
6. Combine lexical and vector candidates, deduplicate by source/fragment and apply
   deterministic rank fusion. Permission/trash/current-version filters apply in both
   retrieval paths and immediately before provider submission.
7. Start with exact filtered vector search and measure; add an ANN index only if
   needed, with owner-filter recall tests. Existing pgvector infrastructure is not a completed index.
8. Expose owner-only index state in the usage page. A failed index does not hide the
   original file or break lexical search. Unavailable/stale semantic retrieval is explicit.

**Verify:** cross-owner and trash exclusion, stale claim completion, content edits,
retries, broker loss, dimensional mismatch, correct prefixes, citations and retrieval
quality on a fixed Russian/English query set. Indexing does not consume Groq calls.
**Done:** AI-UC-04 and truthful owner index diagnostics; original downloads preserved.
**Rollback:** disable semantic retrieval and continue lexical reads; retain source data.

## 11. AI-07: exact confirmed creates

Start with personal-event creation, new-page creation and one event reminder.
Keep edits/deletes/official overrides optional; do not quietly broaden the allowlist.

Add immutable proposals and execution records with exact parameters, source/target
references, expected versions, owner, expiry, capability version and durable idempotency.
The model can request a proposal; it cannot confirm its own proposal.
The planned owner confirmation endpoint consumes an exact proposal ID under CSRF.
Changing parameters creates a new proposal. Recheck current capability policy, owner,
versions and source access before the normal service commits the action.

Persist execution outcome atomically with the business change where they share the
database transaction. A network failure after commit returns the stored result on
retry. Model failure after commit cannot rewrite success as an unexecuted action.
Single-action proposals come first; a multi-action plan needs an explicit transaction
and partial-failure strategy. Cancellation is not a database rollback after commit.

Choose expiry and audit/idempotency retention before implementation; execution records
must outlive every accepted replay window and must not cascade with chat deletion.
Add proposals/committed/stale/failed counts to existing analytics with separate totals.

**Verify:** duplicate confirmation, concurrent manual change, disabled capability,
expired proposal, cross-owner request, rollback and response loss after commit.
**Done:** AI-UC-07/08/09, previews and observable committed results.
**Connect:** existing domain services only; no automatic grant enabled.

## 12. AI-08: optional grants and automatic actions

Defer until a new request selects exact operations, target scopes, parameter/count
limits, expiry and triggers under Q-04a. Example policies in documentation are not grants.
Use the shared execution path from AI-07 and PostgreSQL-backed grants/revocations.
Serialize execution authorization with revocation. A queued task checks again at
execution time. A trigger/schedule is a separate explicit choice; no recurring job
is created merely by granting an operation. Show automatic outcomes and denials in
owner analytics. No private IIS, automatic deletion or implicit permission expansion.

**Done:** grant/revoke/expiry/limit/version/replay tests and exact owner acceptance.
**Rollback:** disable automatic dispatch and revoke grants; preserve committed work/audit.

## 13. AI-09: release and provider replacement rehearsal

- Run the selected scenario suite against fake and explicitly enabled synthetic
  Groq calls. Record model/prompt/tool versions, quality, latency, attempts and tokens.
- Score source support, citation correctness, correct tool/target selection and
  required clarification separately. Security, ownership, unauthorized-write and
  duplicate-action cases must all pass; review answer-quality examples manually
  rather than accepting the model's own success score. Keep a small held-out set.
- Compare 120B/20B manually with identical fixtures. A model change is configuration
  plus regression evaluation; it is not proof of identical behavior.
- Add another LLM adapter only if requested. Keep tool/business contracts unchanged,
  map capability differences and test refusals, truncation, tools and stream cancellation.
- A free Cloudflare BGE-M3 adapter is an optional local-runtime replacement. Its quota
  and data policy must be checked at activation; it is not automatic failover.
- A different embedding model needs a new index generation/dimension migration,
  rebuild, quality check and explicit activation. Keep the old active generation until
  validation succeeds; lexical search remains available during rebuild. Reverting a
  provider setting alone cannot make incompatible vectors usable.
- Verify retention cleanup and deletion do not resurrect content or remove active
  action replay protection. Verify backup/restore on disposable data.
- Record the actual host resource report and provider-account limits; no throughput promise
  follows from free-tier limits. Reconcile estimated costs with provider-console usage manually.

## 14. Verification and documentation for each implemented stage

Follow [current commands](local-development.md#checks). Backend changes require Ruff,
Ruff format, Pyright, pytest, applicable native PostgreSQL/Redis/S3 tests and
`docker compose config --quiet`. Verify the merged home overlay when its wiring changes.
Frontend stages require lint, typecheck, build and browser tests. Preserve ordinary
tests without network access; opt-in provider smoke tests use synthetic data and
explicit runtime activation. Never run trials against private files by default.

Update the product status, actual AI/API/setup documentation, roadmap stage status,
affected decisions and dated verification evidence. Commit only stage-related files
locally after checks; push/deployment needs a request. A documentation-only plan
checks links/status/diff and Compose configuration; it does not claim runtime tests.

## 15. Planning-document verification (2026-10-17)

Executed for this documentation change: local Markdown target/anchor validation,
balanced fences and English-language checks for the new documents; `bash -n` for
the runbook's three Bash blocks; JSON parsing/assertions for the synthetic probe;
`git diff --check`; base `docker compose config --quiet`.
Shell examples were checked for syntax only, not executed. No provider call, model
download, dependency installation, migration, runtime test or deployment was performed.
These checks validate the plan, not an implemented AI capability.
