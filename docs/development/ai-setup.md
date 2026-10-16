# AI Development Setup and Switching Runbook

Updated: 2026-10-17.
Status: instructions for the **planned** [AI stages](ai-implementation-plan.md).
No AI environment setting, application route, embedding worker or CLI is implemented
by this document. Do not paste future settings into today's app expecting AI to work.
Provider console steps and the optional direct vendor probe are independent of Ukladen.
No account was created, model downloaded, key read or provider request executed for this plan.

The selected configuration is Groq Free / `openai/gpt-oss-120b`, CPU
`intfloat/multilingual-e5-small`, PostgreSQL FTS/pgvector and existing Celery.
[Scenarios and analytics](../product/ai.md) remain editable and not implemented.

## A. AI-00/01: prepare the project without external calls

1. Select the scenario rows and source/data policy in the product specification.
2. Use the existing [local development guide](local-development.md), or the already
   configured [home profile](../deployment/home-server.md). Do not overwrite a working
   `.env`/`.env.home`, replace credentials or delete volumes to add AI.
3. Implement AI-01 and apply its reviewed migrations to disposable data first.
4. Only after AI-01 supports these settings, edit the private active environment:

```dotenv
AI_ENABLED=true
AI_LLM_PROVIDER=fake
AI_EMBEDDING_PROVIDER=disabled
AI_ENABLED_CAPABILITIES='[]'
AI_AUTOMATIC_ACTIONS_ENABLED=false
```

5. Run fake-provider backend tests. Check that a synthetic run produces one run,
   the expected provider attempts and honest usage fields. No key should be required.
6. Keep ordinary CI on fake mode; network/provider tests remain explicit opt-in checks.

The current stack can be validated without printing expanded secrets:

```bash
docker compose config --quiet
```

For the home profile, use the `home_compose` function from the deployment guide and
`home_compose config --quiet`. These existing commands do not implement or enable AI.

## B. AI-02: connect Groq Free

### B1. Account and key

1. Open [Groq Console](https://console.groq.com/) and create/sign in to an account.
2. Check the account plan and leave it on Free. Do not activate Developer billing
   or a paid fallback as part of this zero-API-spend setup.
3. Open [API Keys](https://console.groq.com/keys), create a development key and store
   it privately. Never put the key in browser code, source control, screenshots or chat.
4. Open [Limits](https://console.groq.com/settings/limits), select the actual model
   and record the account's RPM/RPD/TPM/TPD and date. Published values may differ.
5. Review [Data Controls](https://console.groq.com/docs/your-data). Enable Zero Data
   Retention where available and record the setting before using private excerpts.
   The laptop being in Switzerland does not mean provider processing stays there.

As checked on 2026-10-17, the published Free table lists 30 RPM, 1,000 RPD, 8,000 TPM
and 200,000 TPD for both GPT-OSS models. These are shared account/organization limits,
not per-Ukladen-user allowances. Use [the live table](https://console.groq.com/docs/rate-limits)
and actual response headers at activation; the model's context capacity is not a free quota.

### B2. Wire only the intended process

AI-02 must first add `.env.ai` to `.gitignore` and explicit API-only secret loading
in both local and home Compose configurations. The existing shared backend env-file
anchor otherwise distributes added secrets to workers and migrations too.
Keep the secret file optional while AI is disabled or fake; require a key only when
Groq is enabled. A non-AI installation must not need a new secret file to start.

After that wiring exists, verify the path is ignored **before** creating the file:

```bash
git check-ignore .env.ai
```

If the command does not report `.env.ai`, stop and fix the ignore rule. Create the
file in an editor with private permissions and enter `GROQ_API_KEY` there. Keep it
out of the normal shared `.env`/`.env.home`. The implementation must document/test
the actual file loading and keep the key out of resolved configuration output.

For host development, inject the key into the API terminal environment; never
`source` an unreviewed env file as shell code. Normal workers, embedding workers,
material extraction children, web and migration processes do not need the Groq key.
If later AI background generation needs it, add an explicit narrowly scoped consumer.

After the adapter/configuration exists, set these nonsecret values in the active profile:

```dotenv
AI_ENABLED=true
AI_LLM_PROVIDER=groq
AI_LLM_MODEL=openai/gpt-oss-120b
AI_EMBEDDING_PROVIDER=disabled
AI_ENABLED_CAPABILITIES='[]'
AI_AUTOMATIC_ACTIONS_ENABLED=false
```

Rebuild/recreate the affected application processes using the existing development
guide. Public deployment still requires its own request, backup and home-profile checks.
Do not add arbitrary provider base URLs supplied by a browser request.

### B3. Optional direct vendor connectivity probe

This Bash example sends one short **synthetic** request to Groq, independently of
Ukladen. Run it only after intentionally choosing to test the Free account. It is
not a test of Ukladen ownership, tools, accounting or UI and is not recorded in the
application usage page. The provider console can therefore show more calls than the app.

```bash
read -r -s -p 'Groq development API key: ' GROQ_API_KEY
printf '\n'
export GROQ_API_KEY
curl --silent --show-error --fail-with-body --max-time 30 \
  https://api.groq.com/openai/v1/chat/completions \
  -H "Authorization: Bearer ${GROQ_API_KEY}" \
  -H 'Content-Type: application/json' \
  --data '{"model":"openai/gpt-oss-120b","messages":[{"role":"user","content":"Reply with one short greeting. This is a synthetic connectivity test."}],"max_completion_tokens":1024}'
unset GROQ_API_KEY
```

Inspect HTTP success, completion/finish status and reported usage. A truncated
completion is not a successful answer-quality check. Keep any saved fixture sanitized.
Use the documented [API quickstart](https://console.groq.com/docs/quickstart) if
the vendor changes this contract.

Then run the AI-02 smoke through the application using a synthetic conversation.
Verify the usage ledger, safe errors and one deliberately simulated 429 in tests.
Never use a private document as the first connectivity test.

## C. AI-03/04: add tools, chat and the usage page

1. Enable `calendar_read`, `workspace_search` and `page_read` only after their
   application adapters, ownership tests and source rendering exist.
2. Add `material_read` only after the new authorized excerpt boundary exists.
   The current original-file download endpoint is not a text retrieval tool.
3. Start with synthetic sources. Record the real-content data policy before private testing.
4. After AI-04, open the planned `/workspace/ai` page and submit the catalog examples.
   The planned `/workspace/ai/usage` page must show your own run and provider attempts.
5. Open a citation in the read-only source drawer; confirm it does not expose trash,
   foreign content or an invented PDF page number. Test an expired session/account change.
6. Check 7/30-day summaries, unknown token usage and fake traffic separation.
   "Free-plan expected cost" is not a provider invoice; list-price estimates have a date.

Do not enable Groq hosted search/code/MCP tools to make these scenarios work.
The selected tools execute through Ukladen's existing application services.
Groq currently excludes tool use/streaming from Structured Outputs; see
[current limitations](https://console.groq.com/docs/structured-outputs).

## D. AI-05: download and measure CPU embeddings

1. Prove compatible CPU dependency wheels under the repository's Python 3.14 and
   container image. Pin tested packages in the backend lockfile/optional embedding
   dependency group; the API embedding runtime and embedding worker need that group,
   normal workers do not. Use the official package/model sources.
2. Pin a resolved revision of [E5-small](https://huggingface.co/intfloat/multilingual-e5-small/tree/main).
   Download weights/tokenizer into a persistent private cache before serving requests;
   a first request must not unexpectedly download a model. Mount the tested cache
   read-only where feasible. Loading cached weights must work offline.
3. After the adapter supports them, configure:

```dotenv
AI_EMBEDDING_MODEL=intfloat/multilingual-e5-small
AI_EMBEDDING_DEVICE=cpu
AI_EMBEDDING_THREADS=2
AI_EMBEDDING_BATCH_SIZE=4
```

The implementation must add and validate `AI_EMBEDDING_DEVICE=cpu`; it must not
silently select the RTX 4060 or install CUDA as the default. Keep the provider disabled
for real retrieval until AI-06 publishes a valid index.

4. Measure cold/warm queries and 100/1,000 synthetic fragments. Record RSS, CPU,
   p50/p95 query time, throughput and swap with the whole Ukladen stack running.
5. Measure both the API query-model copy and the indexing-worker copy together.
   Verify ordinary Celery workers do not load model weights. Do not multiply API
   worker processes without revisiting the memory budget.
6. Compare with the AI-05 targets. If the host cannot meet them, keep lexical mode
   available and choose the free API alternative before publishing embeddings.

No new cloud key is needed for local embeddings. Source indexing must not call Groq.
Thread/runtime optimization follows [Sentence Transformers](https://sbert.net/docs/sentence_transformer/usage/efficiency.html).

## E. AI-06: activate indexing and semantic retrieval

1. Back up source data before applying reviewed migrations to an existing deployment.
   Test migration upgrade/downgrade and rebuild behavior with disposable PostgreSQL first.
2. AI-06 must ship the `embeddings` queue, recoverable job scanner, model-cache mount,
   optional CPU dependency installation and `embedding-worker` in both Compose profiles.
   This service does not exist today. Add exact tested startup/health commands when delivered.
3. Start one indexing consumer and the existing single Beat process. Keep normal and
   material queues on their existing workers. Do not run two Beat instances.
4. Index a small selected synthetic collection. Verify canonical version/location,
   expected E5 prefixes, vector dimensions and owner filters.
5. Set `AI_EMBEDDING_PROVIDER=local` only when a compatible active generation exists.
   Add `material_read`/retrieval capabilities only for delivered scenarios.
6. Search using different wording, open actual source fragments, edit/trash a source
   and verify stale content stops appearing before asynchronous cleanup finishes.
7. Test worker/broker restarts and retries without repeated source ingestion or lost jobs.
8. Index private sources only under the recorded policy; observe owner index status
   and operator memory diagnostics before increasing the batch size.

To pause semantic retrieval, select `AI_EMBEDDING_PROVIDER=disabled` and stop new
index-job dispatch through the implemented control. Preserve source documents and
the last index generation. Lexical search continues with an explicit semantic status.

## F. AI-07 and optional AI-08: connect write operations last

1. AI-07 adds exact proposal/confirmation/execution storage and the planned confirmation
   endpoint. Keep automatic actions disabled.
2. Enable `event_create`, then `page_create`, then `reminder_create` only after each
   preview, normal-service integration, source viewer and duplicate-confirmation test passes.
3. Use disposable content for the first real confirmed create. Check the committed
   object, analytics outcome and retry result after a simulated lost HTTP response.
4. Verify a changed/expired/disabled proposal is rejected. Editing a scenario does
   not authorize a write; the current server capability list is checked at execution.
5. AI-08 requires a separately specified owner-issued grant and trigger. Do not set
   its enable flag merely because AI-07 works. Confirm revocation against queued jobs.

## G. Switch models/providers without losing content

| Change | Required work |
| --- | --- |
| Groq 120B -> 20B | Change `AI_LLM_MODEL`, restart API as needed, rerun selected fixture scenarios and inspect usage |
| Groq -> another LLM API | Implement/test another `LlmProvider`, record privacy/billing policy, configure its secret only for its consumer |
| Local E5 -> same verified E5 API runtime | Prove revision/tokenization/prefix/normalization equivalence before reusing vectors |
| E5 -> another embedding model | New index generation and dimensions if different, complete rebuild/quality checks, then explicit activation |
| Remove an optional scenario | Update catalog, server capability mapping where applicable and UI shortcuts; retain created objects/audit |

Optional free API replacement: [Cloudflare Workers AI](https://developers.cloudflare.com/workers-ai/get-started/rest-api/)
with `@cf/baai/bge-m3`. Create the documented Workers AI token restricted to the intended
account, record current free quota/data policy, add its adapter/secret/configuration
and test a synthetic embedding. Free allocation is shared with other Workers AI use;
check [current prices and model eligibility](https://developers.cloudflare.com/workers-ai/platform/pricing/).
The token and this adapter are not needed for the selected local baseline.
Changing to BGE requires reindexing; never embed queries with BGE against E5 vectors.

## H. Troubleshooting and zero-spend operation

| Symptom | Check / response |
| --- | --- |
| 401/403 from provider | Key/permissions/model access/account availability; keep details out of user responses and logs |
| 429 | Account/model quota and `Retry-After`; bounded retry or explicit waiting state |
| Empty/truncated output | Finish reason and completion budget; do not blindly repeat a write |
| Poor retrieval | Correct query/document prefixes, tokenizer limits, revision and active generation; compare lexical results |
| Memory pressure | Count API/worker copies, batch size and CPU package selection; pause indexing before adding capacity |
| Slow calendar/API during indexing | Measure contention; reduce threads/batch/concurrency; preserve query responsiveness |
| Dashboard differs from console | Direct probes/other apps/shared keys, unknown usage or reporting windows; app totals are owner-scoped |
| Free spend says zero but tokens are missing | Show incomplete usage explicitly; free-plan status does not make token counts known |

Keep only selected Free accounts configured. Bound context/tool results, count attempts,
cache unchanged indexes, and disable unneeded scenarios. Do not use automatic paid
fallback, unlimited retries, or random providers receiving private context. Model
catalog size is not an evaluation result; compare fixed scenarios before switching.

## I. Stage handoff record

For each delivered stage record: commit, implemented settings/routes, exact startup
commands for local/home profiles, executed checks, provider/model revisions, real-call
count, usage completeness, host measurements, rollback action and remaining decisions.
Update this runbook from planned instructions to verified commands only with evidence.
