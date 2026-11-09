# AI evaluations

The required suite runs the existing Ukladen `create_agent` runner and middleware with
synthetic application-port evidence and a scripted model. DeepEval 4.3.3 is pinned in
the separate `evaluations` dependency group; it is not a production dependency.
Python 3.14 and the existing LangChain/LangGraph pins are retained.

## Offline commands

From `apps/backend`:

```bash
uv sync --frozen --extra embeddings --group evaluations
uv run --group evaluations pytest evaluations
uv run --group evaluations python -m evaluations.run --output /tmp/ukladen-ai-evaluations.json
```

The JSON report contains the dataset SHA-256, per-turn assertions, model/tool/read
counts, serialized message size (excluding tool-schema/wire overhead) and elapsed time.
Exit 1 means an objective assertion
failed. The report always says `model_quality_gate=not_evaluated` for scripted runs.
CI runs this suite and saves JSON/JUnit reports separately from the backend regression.
The DeepEval and rerunfailures pytest plugins are disabled: no implicit uploads,
judge selection, automatic retries or plugin socket server are needed. Direct custom
DeepEval `BaseMetric.measure` calls keep reports local. Telemetry, dotenv loading,
legacy key files and Confident AI credentials are disabled before DeepEval imports.
A socket-denied test exercises every offline scenario; no cloud service or judge is used.

`scenarios.json` has 60 cases, five in each of 12 categories: schedule, notes, uploaded
documents, comparisons, extraction, planning, replanning, event confirmation, note
confirmation, multi-step/multi-turn calls, failures, and injection/isolation. Each
case records its setup, expected result/tools/arguments, allowed tools, forbidden
actions and invariants. Inputs and IDs are synthetic; the clock is fixed to 2030-11-04.
Scripts are test stimuli, not a prediction that a real model selects those tools.

## What the scores establish

- Tool correctness compares names; selection checks the allowlist; argument checks
  compare actual parameters; sequence checks order and multiplicity. Missing, extra,
  reordered or altered calls fail dedicated corruption tests.
- Task completion checks the actual terminal state and authored required facts.
  Recovery and fresh-runner HITL continuation have explicit regression assertions.
- Context relevancy/recall compare labeled evidence with the actual model input in
  scripted runs. Exact fact/claim checks provide deterministic answer relevancy,
  faithfulness and unsupported-claim detection on these small authored examples.
  They are strict fixture assertions, **not** semantic-equivalence or general truth
  metrics. Paraphrases can fail them. No LLM judge is hidden behind a score.
- Citation checks require expected source IDs and reject foreign IDs. Provenance is
  not proof that a claim is supported at the cited location; semantic citation quality
  remains a live-review requirement.
- `recall_at_k` and `reciprocal_rank` are independently tested with missing/duplicate
  and wrong-ranked results. The existing real local E5/PostgreSQL benchmark now
  reports Recall@1, Recall@3 and MRR over 12 bilingual labeled queries:

```bash
AI_TEST_DATABASE_URL='<explicitly disposable PostgreSQL DSN>' \
  uv run --extra embeddings python -m benchmarks.semantic_retrieval /path/to/verified/local/model
```

The model directory must already contain the verified artifacts; this command does
not download weights or call a provider. It uses two model instances in one process;
allow 4 GiB for this benchmark. The normal deployment uses separate consumer processes
with their existing limits. Twelve synthetic queries do not establish production RAG quality.

Real PostgreSQL/Redis/S3 safety checks remain the ordinary backend tests, not simulated
DeepEval passes. Configure the documented disposable test variables, then run `pytest`.
In particular, AI actions/persistence/documents/accounting/bounds/tasks and semantic-index
tests cover owner isolation, exact confirmation, rollback, duplicate prevention,
restart recovery, stale sources, cancellation and late-result fencing. The full native
suite must pass as well as the evaluation suite. See the [quality report](../../../docs/development/ai-quality-report.md).

## Live model checks: prepared, not authorized

First copy `live.example.json` to a private local file and select an exact model,
case IDs, streaming mode, request count, byte/output bounds and verified route-price
ceilings. Replace the example approval reference with the owner's concrete bounded
approval. A string in a file is an audit reference, **not** permission by itself.
The existing catalog validator rejects routers, hosted-search suffixes and dynamic
latest aliases. Application credentials, catalogs, production databases and user
content are never loaded by this harness.

The following command is a dry run and makes zero provider requests:

```bash
uv run --group evaluations python -m evaluations.live --config evaluations/live.example.json
```

Only after the separate owner approval required by `AGENTS.md`, supply a dedicated
`UKLADEN_EVAL_API_KEY` through the environment and run:

```bash
uv run --group evaluations python -m evaluations.live \
  --config /private/approved-evaluation.json --execute --output /private/live-results.json
```

No live execution was authorized by implementing this command. It never approves a
business proposal: tools stop at the same HITL boundary. Network calls go through the
normal guarded OpenRouter adapter, with its SDK retries/fallbacks disabled and explicit
prompt/completion price ceilings plus zero per-request fee. The shared locked budget
reserves each dispatch, including every tool-loop call, before credentials are returned.
A failed/unknown attempt does not refund its reservation. A new run requires new
approval when the earlier allowance is exhausted. No paid search or LLM judge is used.
Provider 429/503 backoff stops the suite without sleeping or retrying another case.

The reservation uses serialized input bytes as a conservative token bound and the
configured output bound. It is an estimate under the supplied provider pricing and
routing contract, **not** a provider-account billing limit or a per-model tokenizer
proof. Verify the model's accounting/prices and use the account's spending controls
when authorizing an operation. Missing usage must remain unknown. The report records
reserved requests/cost, not an invented actual invoice.

Live reports contain observed answers and tool arguments for human review, use mode
0600 and refuse existing output files. Even a perfect objective result retains
`requires_semantic_and_safety_review`: reviewers must assess paraphrases, unsupported
claims, citation support, ambiguity and injection behavior. In live mode contextual
checks use checkpoint tool results; they do not claim observation of the exact
provider wire context. Streaming and structured-output adapter unit tests use mocked
HTTP; they do not certify support for every model in the operator catalog.
