# AI Implementation Plan

Updated: 2026-10-24.
Status: AI-00 and the offline AI-01 foundation are delivered: a fake-only harness,
owned persistence, authenticated chat/run API, durable accounting, bounded execution,
conservative recovery and physical retention cleanup. Tested on disposable
PostgreSQL/Redis, disabled by default and unapplied to the running app.
AI-02 now adds the optional [OpenRouter catalog and encrypted connections](ai-connections.md);
activation/live account verification remain pending. AI-03 adds implemented
[authorized source reads](ai-03.md). [AI-04](ai-04.md) adds locally implemented
streaming chat/settings/usage UI and API; subsequent stages remain not implemented; see the dated final verification in the
[execution record](ai-01-execution-plan.md#13-final-ai-01-verification-2026-10-24).
No P-06, real provider traffic or deployment is included.

Read [system architecture](../../SYSTEM_ARCHITECTURE.md), [AI architecture](../architecture/ai.md),
[product scope](../product/ai.md), [ADR 0005](../adr/0005-support-scoped-ai-action-permissions.md),
[ADR 0009](../adr/0009-specify-provider-neutral-ai-orchestration.md),
[tool contracts](ai-tool-contracts.md) and [setup](ai-setup.md).

## 1. Delivery map and dependencies

Existing stage IDs remain stable. New stages make the owner's broader target explicit;
numeric order is not an implicit dependency or authorization to start another stage.

| Stage | Deliverable | Dependencies / connection gate | Exit evidence |
| --- | --- | --- | --- |
| AI-00 | Agreed scope, policies, tool/config contracts and synthetic cases | No external connection | Specification/fixture/link checks; no runtime claim |
| AI-01 | Delivered offline agent, owned chat/run API, persistence, accounting, bounded recovery and retention; disabled by default | AI-00; all nine steps individually approved; no application migration/activation | Offline/native lifecycle, restart and cleanup checks; dated final verification in the execution record |
| AI-02 | Implemented optional OpenRouter catalog, supported adapter and encrypted personal connections; live activation pending | AI-01; owner-selected OpenRouter/DeepSeek; account gate remains | Synthetic HTTP/native secret/quota/isolation checks; [contract](ai-connections.md) |
| AI-03 | Implemented authorized page/material/calendar/database tools and lexical grounding; unactivated | AI-01/02; existing application services | Native ownership/lifecycle, synthetic provider/API, current-context and citation checks; [contract](ai-03.md) |
| AI-04 | Implemented local streaming chats, cancellation, sources, instructions/model settings and usage UI; unactivated | AI-01/02/03 | [Contract and verification](ai-04.md) |
| AI-05 | Embedding runtime/hardware proof | AI-00; model download only if requested | Compatible packages, pinned model and measured full-stack cost |
| AI-06 | Versioned chunks, hybrid retrieval, complete-source coverage support | AI-03/05; pgvector/index jobs | Retrieval quality, lifecycle/recovery and coverage checks |
| AI-07 | Exact confirmed creates and requested edits | AI-01/03/04; each target service must exist | Normal-service writes, versions, commit/replay and previews |
| AI-08 | Opt-in automatic page/task creates with scoped grants | AI-07; tasks also need AI-10 | Revocation/expiry/limits/queued-job checks |
| AI-09 | Release hardening and provider replacement rehearsal | Every capability being released | Evals, failure/recovery, secret/retention and owner acceptance |
| AI-10 | Task extraction, deterministic planning/replanning and atomic plan application | P-06; AI-03/04/07; AI-06 for semantic material retrieval | Feasible/infeasible plans, protected events, races and atomic rollback |
| AI-11 | Labeled knowledge fallback and bounded web search | AI-03; explicit search adapter contract | No-evidence vs failed search, citations, egress and injection checks |
| AI-12 | Opt-in proactive reviews and in-app delivery | AI-04; AI-10 for task/workload reviews | Bounded/deduplicated triggers, disable/restart and quiet unchanged runs |

AI-01/02/03/04 form a lexical prototype, not the complete agreed assistant. Add
AI-05/06 and AI-11 for the selected semantic/multi-document/fallback experience.
AI-07 adds writes; P-06 and AI-10 are mandatory for the selected planning scenario.
AI-08/12 remain user opt-in capabilities, not omitted target features. Run AI-09
checks for every promoted capability. Stop at each requested stage's completion report.

## 2. Places each implementation must reach

| Area | Responsibility / reuse |
| --- | --- |
| ai module | Conversation/run/proposal/grant/settings/usage orchestration and application ports |
| ai infrastructure | LangChain create_agent/tools/HITL on LangGraph, PostgreSQL checkpoints and recovery; no framework types in domain/application |
| LLM integrations | Concrete supported adapters; normalized requests/results and capability mapping |
| search | Existing lexical service, derived chunks/embeddings, coverage and web-search application port |
| embedding/web integrations | Independent implementations; no implicit shared keys or billing |
| tasks / calendar | Typed state/planning and authoritative interval/conflict application interfaces under P-06 |
| notes/relations/workspace/reminders | Existing validation, versions, ownership and transaction participation |
| core config/composition, Alembic | Typed settings, delivered transport/dependencies, constraints and preserving migrations |
| workers/Compose/home profile | Explicit queue/process/secret consumers; preserve existing mail/material/reminder workers |
| web/auth/cache | Same identity boundary, A1 brand, Russian product text, chat/source/settings/usage UI |
| dependency lock / CI | Compatibility proof before framework/SDK/embedding dependencies; offline ordinary tests |
| fixtures/docs | Evolving acceptance cases, real implemented API/setup and dated verification |

A material download returns original bytes, not an authorized extracted-text tool.
Add a bounded excerpt application contract. Page-page/task links and planner APIs
are not already implemented merely because package markers or tables are planned.

## 3. Planned configuration and bounds

AI_ENABLED, AI_RETENTION_ENABLED, AI_LLM_PROVIDER and AI_LLM_MODEL preserve the
offline default. Optional AI_CONNECTIONS_FILE adds the delivered catalog/secret-file configuration. Other settings below remain planned; add only those needed
by the delivered stage, with no empty future plugin system.

| Setting / configuration | Initial contract |
| --- | --- |
| AI_ENABLED | false; fake is the offline default when enabled |
| AI_RETENTION_ENABLED | false; after approved migration, keeps worker recovery/cleanup enabled independently of chat |
| AI_LLM_PROVIDER / AI_LLM_MODEL | fake / fake-v1 initially; real adapters/models are explicit operator entries |
| Operator connection/model catalog | Versioned supported provider/model entries, capability profile and secret reference; AI-02 |
| Personal connection | Owner-scoped encrypted credential, supported adapter/model and disconnect state; AI-02 |
| AI_ENABLED_CAPABILITIES | Empty until corresponding tools/services are delivered |
| AI_EMBEDDING_PROVIDER / AI_EMBEDDING_MODEL | disabled / unset until AI-05 proof; local CPU E5-small is a candidate, not a provider coupling |
| AI_AUTOMATIC_ACTIONS_ENABLED | false; enabling dispatch never creates a grant |
| Web search connection | Disabled until an explicit adapter, credentials and bounded egress exist; AI-11 |
| Run/input/tool budgets | Versioned defaults in [tool contracts](ai-tool-contracts.md#3-initial-execution-budgets) |

Use the lower of application limits and verified adapter/account limits. Requests,
tokens and actual price/budget policy are configured per connection before activation.
A free label is not a zero-bill guarantee; no silent paid/provider/credential fallback.

## 4. AI-00: specify the agreed system

Delivered on 2026-10-21: updated product/architecture/decisions, provider-neutral setup,
selected scenarios, prompt/tool version identifiers, bounded tool contracts and
[synthetic acceptance data](../../apps/backend/tests/fixtures/ai/ai-00.json).
The fixture is input/expected-outcome data, not a passing behavioral test suite.

Owner decisions include RAG-first/labeled fallback, implicit relevant-data transfer
when using AI, separate chats with 30-day user-message inactivity expiry, 30-day
content-free activity, independent tasks, editable 45/15 sessions with explicit work
windows, personal instructions and both operator/BYOK models. Delegated policies
allow only conditional planning on stale coverage and automatic new-page/task creates.
Plans revalidate and commit as a whole; personal appointments remain fixed by default.

Remaining implementation gates are specific, not reopened product choices: actual
vendor/search endpoints and models, account prices/quotas, encryption implementation,
embedding/runtime compatibility and freshness thresholds. AI-01 proves framework
compatibility and retains minimal replay/context markers until account deletion.
Keep external integrations disabled until their gates are verified. AI-00 requires
no API key or private content, and does not implement the selected functionality.

## 5. AI-01: offline orchestration, persistence and accounting

Status: complete within the approved offline scope. The framework-neutral AgentRunner
port and input/result/review DTOs isolate LangChain create_agent, typed synthetic tools,
HumanInTheLoopMiddleware and PostgreSQL checkpoints in infrastructure. Python 3.14
compatibility and pinned dependencies are verified. There is no custom model/tool loop.
Synthetic approve/reject resume is tested across fresh processes; production actions
and public confirmation/resume transport remain AI-07/08.

Owned conversations/messages, runs, provider attempts and tool outcomes use Alembic
revisions 0022/0023, applied only to disposable data. Checkpoint schema is reviewed in
migrations, never created on API startup. The [persistence contract](ai-persistence.md)
describes owner constraints, short transactions, deletion and minimal replay receipts.
No action/grant tables are added.

The authenticated [offline API](ai-api.md) uses existing completed-registration,
session, CSRF/Origin and no-store contracts. It enforces bounded input, server-derived
identity, one active run/chat, exact submission replay and cancellation. Admission
precedes execution; no transaction spans a model call. The journal counts actual
attempts, including bounded retries, and preserves unknown usage as NULL.

Durable deadlines, late-result barriers and conservative reconciliation close overdue
work without replaying uncertain effects. Thirty-day content and independent activity
cleanup is bounded and idempotent. Minimal owner/run/submission IDs and a completed
marker survive detailed journal cleanup until account deletion. Maintenance can stay
enabled independently of chat. See [setup and limitations](ai-setup.md).

The owner requested approval before changes and permits read-only checks without
additional confirmation (clarified on 2026-10-22).
Follow the [AI-01 approval checkpoints](ai-01-execution-plan.md): report the completed
step, checks and exact next scope, then obtain approval before subsequent changes.
All nine steps were individually authorized and completed; the execution record
preserves each checkpoint and [final verification](ai-01-execution-plan.md#13-final-ai-01-verification-2026-10-24).

The current narrow boundary is AgentRunner. Real model normalization/capability and
credential contracts belong to AI-02; embedding and web-search ports belong to
AI-05/11. These interfaces are added with their implementations rather than as empty
AI-01 wrappers. Framework/SDK types must remain outside domain/application contracts.
Real adapter transport timeouts are required before activation: a timed-out synchronous
fake call keeps its bounded thread slot until it returns. No real model, business
tool, source retrieval, streaming or product UI is delivered by AI-01.

## 6. AI-02: operator models and personal API connections

Status: implemented locally through the [AI-02 contract](ai-connections.md); disabled by
default, with application migration, live provider/account proof and activation pending.
The owner selected OpenRouter/DeepSeek and delegated adapter expansion/access details;
model changes use new chats and private setup/test artifacts stay out of commits.

Implement the operator catalog plus owner-only create/list-masked/disconnect personal
connections. Verify one chosen vendor's documented contract rather than assuming all
APIs are interchangeable. Account/model selection is explicit; endpoint selection is
restricted to supported adapters, not arbitrary browser-provided base URLs.

Prove tool schemas, refusal/truncation, structured-output and streaming behavior for
each model profile. Stage separate structured requests where the adapter requires it.
Reject incompatible modes; never dispatch partially streamed arguments as actions.

Use consumer-scoped operator secrets and authenticated encrypted BYOK persistence.
Document master-key provisioning/rotation, masking, disconnect/revocation, backup
handling and failure when credentials cannot be decrypted. Secrets never enter
checkpoints/prompts/client responses/logs or other users' records.

Bound timeouts/retries, count actual provider attempts and enforce per-connection
admission. Honor provider retry headers without indefinitely sleeping in HTTP handlers.
Ordinary CI uses fake credentials/providers; one intentionally activated synthetic
smoke records actual usage and safe failures. No private file or automatic paid fallback.

## 7. AI-03: authorized reads and lexical grounding

Status: implemented locally, including optional typed database queries. See the
[AI-03 contract](ai-03.md). Disabled and unmigrated in the running application;
synthetic verification does not prove real-model answer quality. The original scope follows.

Implement the delivered subset of [tool contracts](ai-tool-contracts.md): resolved
calendar, workspace search, page read and new bounded material excerpts. Optional
database reads reuse actual typed workspace interfaces. No P-06 availability/task
advertisement before those application services exist.

Resolve dates in profile timezone and preserve warnings. Every request rebuilds
source context from current owner/access/trash/version truth. Expired citations,
old tool bodies and source-derived summaries cannot bypass current access. Track
coverage so top-k snippets never masquerade as a full document or exhaustive search.
Distinguish no evidence, partial evidence and source/index failure; no automatic
external fallback on authorization failures. Test injection, foreign IDs and source errors.

## 8. AI-04: streaming chat, settings, sources and usage

Status: implemented locally; default-disabled and unactivated. See the
[AI-04 contract and verification](ai-04.md). The original scope follows.

Deliver separate chats, continuation, streaming, safe progress, cancellation and
reconnection to stored state, not duplicate submissions. Polling may aid recovery
but does not replace the selected streaming experience. Partial tool arguments are
never executable. Logout/account changes discard all private state and requests.

Add model/connection settings and editable personal instructions. Instructions are
user preferences, never a replacement for server authorization. Hard planning
preferences become structured settings under P-06. Read-only source viewer uses
existing blocks/excerpts without a full editor rewrite or unsafe HTML.

Deliver owner-only /workspace/ai/usage summary, daily series/recent-run pagination and
safe run details with 7/30-day presets, maximum 31 civil days, profile timezone and
accessible tables. Implement the [usage metric rules](../product/ai.md#9-providers-credentials-and-usage-page).
Test missing usage, retries, price snapshots, fake separation, owner isolation, DST,
retention, credential masking and desktop/mobile keyboard behavior.

## 9. AI-05: embedding runtime proof

Local CPU multilingual E5-small remains an implementation candidate. Prove compatible
CPU packages under Python 3.14/Docker before choosing dependencies; no silent downgrade
or CUDA install. Pin model/tokenizer revision, dimensions, normalization and tokenizer
budgets. Use the model's documented query/document prefixes when required.

Measure lazy single-process API query and separate indexing worker together: two
model copies, bounded inference outside the async loop, two threads/instance and
batch four as initial candidates. Record cold/warm p50/p95, throughput, process RSS,
full-stack memory/swap/CPU and API responsiveness on synthetic input. Initial targets:
no sustained swapping/OOM, warm query p95 <= 1 second and unrelated API p95 degradation
<= 20%. These are targets, not benchmark results. Choose an API/alternative runtime
only with its own contract/data/budget checks if local inference is unsuitable.

## 10. AI-06: versioned hybrid retrieval and coverage

Search owns derived chunks/index jobs with owner/source/version/location, hashes,
chunker/tokenizer/model revision and dimensions. Use Alembic, durable dirty-source
tracking/scanning, fenced claim/compute/complete, bounded retries and restart recovery.
Compute outside transactions and publish only still-current versions. Immediate
canonical ownership/trash/version checks protect both lexical and vector paths.

Use a dedicated embedding queue/consumer only after proof, preserving other workers.
Fuse lexical/vector candidates and deduplicate deterministically; measure before
adding ANN indexes or rerankers. Model changes require a new validated generation
and rebuild, not mixed embedding spaces. Lexical mode survives indexing failures.
Add bounded incremental full-source reads/coverage for summaries and document comparisons.
Test bilingual retrieval/citations, incomplete coverage, source edits/deletion and recovery.

## 11. AI-07: confirmed creates and requested edits

Start with new pages, personal events and reminders, then selected note edits and
explicit personal-event changes. Each operation requires the existing module service,
exact before/after preview, immutable proposal, expected versions, expiry and owned
confirmation. No automatic write merely because a user enabled AI.

Persist outcomes/idempotency with business commits; response loss returns the stored
outcome on retry. Revalidate owner/capability/source truth. Editing invalidates prior
confirmation. Set proposal expiry and minimal replay-record purge explicitly before
migrations; normal 30-day analytics/chat cleanup cannot make old IDs executable.
After commit, cancellation/provider failure cannot erase the successful result.

Task/relationship writes wait for actual target services. Multi-action application
requires one transaction and availability serialization: apply everything or nothing,
then issue a new preview on stale data. No partial success disguised as a complete plan.
Test duplicate confirmations, concurrent changes, expiry, capability disabling,
rollback, crash recovery and lost responses.

## 12. AI-08: scoped automatic creates

The initial delegated allowlist is new-page and new-task creation in selected scopes;
task registration waits for AI-10. Existing edits/event moves/deletes remain confirmed.
Implement owner-issued operation/scope/parameter/count/expiry grants and explicit
triggers, with PostgreSQL authority and serialization against revocation. Settings
instructions cannot grant tools; queued jobs recheck at execution. Missing fields
fail closed; granting an action never creates an unspecified recurring schedule.
Test revocation/limits/expiry/queued replay. Dispatch stays disabled until real grants.

## 13. AI-09: hardening and provider replacement rehearsal

Run fixed and held-out synthetic evals for source support, citation correctness,
target/tool choice, extraction/plan validity, uncertainty and security. Hard failures
include cross-owner data, unauthorized writes, duplicate effects and constraint
violations. A fluent answer or the model's self-score is not evidence of correctness.

For every adapter/model, rerun the same fixtures and actual feature-profile checks.
Verify replacement leaves tool/domain contracts unchanged and no private metadata
crosses credential boundaries. Recheck account limits/terms and compare console
usage honestly. Test backups, retention cleanup, credential disconnect/key rotation,
worker/broker restart and embedding generation replacement on disposable data.

## 14. AI-10: extraction, planning and atomic replanning

Requires P-06 task CRUD/status/subtasks/dependencies/source-link interfaces, work blocks,
occupied/free intervals, conflict checks and structured work preferences. LLM extraction
returns validated proposals with real source locations, ambiguity and labeled estimates.
Checkboxes/records never silently become tasks; elapsed sessions do not complete them.

Use a deterministic task planning service inside the monolith. Start with the smallest
verifiable algorithm; justify OR-Tools only for concrete constraint/optimization needs.
Respect explicit windows, 45/15 defaults, deadlines, breaks/dependencies and protected
events. Preview alternatives or unmet work, not invented feasibility. Stale/missing
coverage allows a conditional preview only; affected application waits for revalidation.

Apply multi-session plans and execution records in one shared transaction, serializing
against concurrent manual busy-event changes as well as task versions. Recheck
availability/constraints under the same protection; any failure applies nothing.
Verify touching intervals, timezone/DST, two concurrent plans, new manual events,
protected training, missed sessions, infeasibility and whole-plan rollback/replay.

## 15. AI-11: bounded web fallback

Implement a documented search adapter behind search.application; no invented endpoint
or unrestricted HTTP/shell tool. For relevant workspace questions, retrieve locally
first, disclose missing evidence and distinguish general knowledge/web claims.
Explicit source-only requests do not expand. Search queries minimize private context.
Bound result count/bytes/deadline, handle redirects/untrusted URLs safely, block
internal-network fetching and cite only retrieved pages. No source credentials or
arbitrary note-driven URLs. Test no-match vs unavailable retrieval, malicious results,
URL validation, absent web capability and no fabricated private facts/citations.

## 16. AI-12: opt-in proactive reviews

All proactive features start disabled. Users choose review types, schedule/timezone
and frequency. Existing Celery/Beat/in-app infrastructure owns bounded scans and
replay-safe delivery. Workload/conflict reviews need P-06/AI-10; source briefings need
retrieval. Call models only for relevant changed state within budgets. No notification
spam on unchanged/non-actionable input. Disabling/revoking/disconnecting stops queued
future work; preserve truthful outcomes of already committed actions.

## 17. Verification and stage reporting

Follow [current checks](local-development.md#checks). Backend runtime stages require
Ruff/format, Pyright, pytest and relevant native service tests. Frontend stages require
lint/typecheck/build/browser tests. Validate base Compose and affected home overlays
quietly. Provider smoke is explicit opt-in with synthetic input; never read real keys
or private sources during ordinary tests.

Documentation-only checks cover relative links/anchors, status consistency, English
technical text, fixture integrity, diff whitespace and docker compose config --quiet.
Do not report behavioral/runtime tests as passed from static contract validation.
Update actual contracts/status/dated evidence and make a cohesive local commit;
push/deployment and the next runtime stage require a request.

## 18. Historical planning-document verification (2026-10-17)


Executed for this documentation change: local Markdown target/anchor validation,
balanced fences and English-language checks for the new documents; `bash -n` for
the runbook's three Bash blocks; JSON parsing/assertions for the synthetic probe;
`git diff --check`; base `docker compose config --quiet`.
Shell examples were checked for syntax only, not executed. No provider call, model
download, dependency installation, migration, runtime test or deployment was performed.
These checks validate the plan, not an implemented AI capability.

## 19. Specification verification (2026-10-21)

Executed: relative Markdown target/anchor validation for 14 changed/new documents
(226 links/anchors), balanced-fence and English-addition checks, JSON parsing/reference
checks for 36 synthetic acceptance cases, UUID/stage/scenario/tool/source integrity,
30-day inactivity boundary, ambiguous DST input and infeasible-capacity fixture checks;
current runbook Bash syntax, verbatim preservation of dated verification history,
git diff --check and base docker compose config --quiet.

These are documentation/data integrity checks, not executed agent behavior. The
2026-10-17 verification text above is retained as dated history. No dependency
installation, migration, backend/frontend runtime suite, model download, external
provider call, API-key extraction or deployment was performed for this specification.
