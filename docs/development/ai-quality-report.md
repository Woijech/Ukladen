# AI quality audit

Date: 2026-11-09. Scope: local audit and verification; real-model acceptance remains pending.
No application deployment, migration, provider activation or real provider request is
part of this work. All persistent checks use separate disposable services and synthetic
credentials. The modular monolith, application tools and existing API contracts remain.

## Baseline and findings

The existing implementation already has one LangChain `create_agent` loop, bounded
calls, owner-scoped PostgreSQL checkpoints, independent exact action proposals/receipts,
atomic service writes, versioned indexing, pgvector/lexical RRF, complete-source jobs,
deterministic planning, public-search isolation, opt-in reviews and owned diagnostics.
No second agent runtime or new service is needed.

| Priority | Reproduced defect | Correction and evidence |
| --- | --- | --- |
| P1 | SSE did not apply JSON mode's tool-argument checks; SDK parsing accepted arrays/null as empty arguments. Multiple streaming choices were silently reduced to the first. | Shared raw JSON-object/identifier validation for JSON and assembled SSE calls; reject multiple SSE choices. Seven new adapter cases reproduced six failures before the fix. |
| P1 | A source could change between refreshed tool reads and the prior complete-source analysis, mixing two versions in one model input. | Compare both evidence sets and omit conflicting evidence with an explicit warning. Focused regression failed before the fix. |
| P2 | A thrown web-search failure left the per-request search budget unused, permitting repeated external attempts. | Reserve the one-query cache slot before dispatch; retain an unavailable result after failure. A regression verifies one dispatch, distinct-query denial and reset on a new request. |
| P2 | A matched chunk's first 600 bytes could exclude the query match and its supporting fact. | Reuse PostgreSQL `ts_headline` for located chunk snippets. Native regression places the matching fact after a long introduction and fails on the baseline. |
| P2 | Complete-source processing repeatedly encoded the entire remaining source to obtain 1500 bytes. | Encode at most the next 1500 characters. Native whole-source continuation test also covers emoji and combining characters. |
| Test infrastructure | A login test compared sessions issued with a fixed October clock against the real clock, failing after their expiry. | Use the same existing fixed clock in its login helper; authentication runtime is unchanged. |

The OpenRouter tests also retain exact model identity, no credential/model fallback,
output/byte/stream bounds, structured-output capability checks, sanitized 429/5xx,
usage preservation on failures and confirmation continuation. No claim is made that
all configured real models support these modes; catalog flags require live verification.

Implementation files: [provider adapter](../../apps/backend/src/app/integrations/llm/openrouter.py),
[tool context/budgets](../../apps/backend/src/app/modules/ai/infrastructure/grounding.py),
[hybrid snippets](../../apps/backend/src/app/modules/search/infrastructure/hybrid.py),
[document steps](../../apps/backend/src/app/modules/ai/infrastructure/document_jobs.py),
and the [test-only clock helper](../../apps/backend/tests/test_auth_login.py).
Tool descriptions now state excerpt character limits/pagination, and whole-source
instructions identify the actual chat mode rather than suggesting a nonexistent tool.

## Evaluation integration

[Evaluation guide](../../apps/backend/evaluations/README.md) contains commands and exact
metric limitations. DeepEval 4.3.3 is pinned in a separate dependency group and locked
with Python 3.14. The solver also selects compatible Click/Hugging Face Hub versions;
LangChain, LangGraph and provider SDK pins are unchanged. Mandatory evaluations use
custom deterministic DeepEval metrics, not an LLM judge or paid cloud service.

The new dataset has 60 synthetic cases across the requested 12 categories and explicit
expected/allowed/forbidden behavior. Every case runs through the production framework
runner, with synthetic application-port fixtures. Corruption tests ensure bad calls,
arguments/order, foreign citations and unsupported authored claims fail. Dataset loading
validates expected HITL proposals against the production action schema, because the
interrupt occurs before tool argument validation. A separate live harness uses only a
dedicated evaluation key, fixed model, explicit cases, shared
request/cost reservations, route-price ceilings and private local reports. Its default
is a zero-request dry run. Offline reports cannot satisfy the real-model quality gate.

Safety evidence is layered: DeepEval asserts fixture contracts; native tests exercise
real services, owner/CSRF boundaries, exact confirmations, atomic rollback/replay,
fresh-process checkpoints, cancellation, document leases and late-result rejection.
Neither scripted injection responses nor source references establish real-model
injection resistance or semantic faithfulness.

## Current verification

Baseline commit: `7d27f469b803142cacded4bdefee1800aea8d718` (clean at task start).
The full unchanged native suite produced **2089 passed, 1 failed** in 724.94 seconds;
the only failure is the fixed auth-fixture clock. An earlier test mount omitted the
editable-package path used by the isolated parser child; those infrastructure failures
were corrected before this baseline. No material validation was relaxed.

| Check | Executed result |
| --- | --- |
| Full backend + evaluation regression | 2192 passed, no failures/errors/skips, 734.57 seconds: 2105 backend tests + 87 evaluation tests on isolated PostgreSQL/Redis/S3. |
| Focused before/after probes | Identical 14 probes: 13 failed / 1 passed on the baseline; 14 passed after fixes (2.83 seconds). |
| DeepEval infrastructure/contract tests | 88 passed, no skips, 3.41 seconds after the final dataset-schema check. Includes budget/backoff mocks and metric corruption cases. |
| Scripted scenario run | 60/60 scenarios, 65 turns; all applicable objective assertions pass. Model-quality gate remains `not_evaluated`. |
| Ruff / formatting | Passed; 565 Python files checked for formatting. |
| Pyright | 0 errors, 0 warnings, using the project's include/rules and the isolated locked evaluation environment. |
| Dependency lock/install | Offline `uv lock --check` passed; `uv pip check` verified 141 compatible installed packages. |
| Compose | Base and home + AI/retrieval overlays validated quietly with example files and synthetic placeholders. No service activation. |
| Documentation / whitespace | Local documentation links and `git diff --check` passed. |
| Real LLM/search requests | 0. Live harness dry run reports 0 requests; all transport tests use mocks. |

The combined run used a frozen source snapshot. The later stream diagnostic-label
and evaluation initialization refinements were separately checked with all 57 adapter
tests, all 87 evaluation tests, the 14 native defect probes, Ruff and Pyright. The final
dataset-schema check adds one evaluation test; all 88 evaluations then passed. Frontend
checks and a fresh broker/worker crash rehearsal were not rerun; no frontend code
changed. Native fresh-process checkpoint/lease/replay/cancellation tests did run.

The scripted run observed 151 fake model calls and 101 requested tool calls across
60 scenarios; median two fake model calls per scenario. It performed 212 application
reads including authorization/source revalidation. Median total scenario latency was
11.679 ms. Median serialized message input was 10,121 bytes per scenario, **excluding
tool-schema/wire overhead**. These are fixture/runtime observations, not real model
latency, token use or a production cost estimate. Unknown token usage remains unknown.

The real local CPU E5/tokenizer/PostgreSQL benchmark used six multi-chunk synthetic
sources and 12 bilingual queries, on an internal network with a 4 GiB process limit:

| Measurement | Before | After |
| --- | --- | --- |
| Expected source ranked first | 12/12 | 12/12 |
| Recall@1 / Recall@3 / MRR | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 1.0 |
| Indexing | 5.859 s | 5.536 s |
| Query median | 38 ms | 41 ms |
| Query max, including cold model load | 1.850 s | 1.878 s |

These single small runs establish no ranking regression, not a general speed or
semantic-quality improvement. The separate excerpt regression verifies that the
matching fact survives the returned snippet. No reranker benefit was demonstrated.

A synthetic fragment-only microbenchmark compared 963 ranges of a 960,000-character
Unicode string and asserted identical output: 0.58524 seconds before versus 0.00364
seconds after. This removes repeated suffix encoding; it is not an end-to-end document
processing speedup. Database reads, model calls and lossy summary steps still remain.

Upstream LangChain/Pydantic-v1 and DeepEval Python 3.14 deprecation/syntax warnings
remain visible; they are not hidden by weakened assertions. Earlier verification
history in AI-05/06/09/10/11/12 is preserved and is not represented as rerun evidence.

## Scenario coverage and remaining gates

| Requested scenario | Local evidence and practical limit |
| --- | --- |
| Schedule/free time/lab preparation | Calendar/availability tools and deterministic planner are implemented and tested. Missing official schedule coverage produces conditional previews and blocks affected application. |
| Extract tasks/deadlines from lectures | Source provenance and exact task confirmation use the existing services. Extraction accuracy/recall requires real-model review; ambiguous dates stay explicit. |
| Replan remaining work | Native planner tests cover deadlines, priorities, dependencies, remaining work, pinned sessions, competing plans and stale availability. Real-model selection of those tools is not proved by fakes. |
| Compare lecture and teacher presentation | Complete-source jobs visit all available extracted text and recover their cursor. Reading all text does not guarantee exhaustive findings; intermediate summaries are lossy, with no OCR. Small evaluation comparisons exercise short sources only. |
| Move an event and related tasks | Supported event/task field edits can share exact action batches. Personal events may intentionally overlap; this is not a conflict-free rescheduling guarantee. A saved task-session plan must be its own action batch; one atomic event-move-plus-task-plan operation is not implemented and is not reported as successful. |

Live gates remain tool selection/argument quality, model-specific streaming/structured
outputs, semantic answer/citation support, long-document comparison/extraction,
ambiguous requests, prompt injection compliance and end-to-end search quality. No
provider call is permitted until a concrete bounded operation is separately approved.

Automatic grants/writes remain deferred. Arbitrary external providers, private IIS,
OCR, formulas, collaboration and automatic synchronization of notes/tasks are outside
the implemented contracts. This audit does not invent them to satisfy a scenario.

## Observability and architecture decisions

Phoenix was assessed against its [official repository](https://github.com/Arize-ai/phoenix).
It supports local tracing, but adding another SDK/exporter/collector is not justified
by a measured gap in this slice. Existing owned opt-in diagnostics retain bounded
model/tool requests/results, timestamps, errors and provider usage locally, with the
existing access and retention rules. Evaluation reports add counts, sizes and latency.
No private source context is exported; LangSmith tracing stays disabled in AI runners.
Phoenix integration is not implemented.

No reranker, query-rewriting model, corrective-retrieval loop, ANN index, vector-database
replacement, new queue or microservice was added. The measured excerpt defect has a
small deterministic fix using an existing helper. More retrieval stages would require
a representative labeled corpus and measured quality benefit, not assumed improvement.

A synchronous timed-out handler cannot be forcibly stopped by a Python thread; actual
transport deadlines and application cancellation/lease/version checks remain essential.
Serialized byte bounds are not per-model context tokenizers. The live evaluator's
cost reservation is not a provider-account billing guarantee. These limits and real
LLM quality must remain visible in any activation decision.
