# Prepared home AI activation

Updated: 2026-10-29.
Status: deployment configuration, images, local artifacts and database schema prepared;
application AI activation and live-provider quality are not performed or verified.

## Spending and personal connections

The owner selected a **USD 5 lifetime cap on the shared application OpenRouter key**,
without an automatic reset, until manually increased. The owner reports that the
cap is already configured in OpenRouter; this was not independently checked against
the account. Confirm that its reset is unset, and that the selected key has available
credit, before activation. This is a provider-enforced key cap, not a local estimate
of remaining dollars or a per-user allowance.

OpenRouter documents `limit: 5` and `limit_reset: null` for this configuration in its
[key update contract](https://openrouter.ai/docs/api/api-reference/api-keys/update-keys).
Key administration requires a management key or the owner's dashboard session; an
ordinary inference key cannot change its own limit. No management key was requested
or stored. Keep the dedicated application key separate from other workloads.

All requests using that key share its provider cap, including chat, document analysis,
web search and reviews. A user's own OpenRouter connection uses that user's credential;
it has no Ukladen product request/token allowance and consumes none of the application's
shared-key budget. Its provider balance/rate limits still apply. Neither a failed
personal connection nor an exhausted application key silently switches payer.

The app's token-cost estimate is not the provider invoice or a hard spending guard.
User quota persistence and an in-app operator budget editor are **not implemented**;
the existing access-policy boundary and usage accounting support a later slice.

## Prepared files and processes

- `.secrets/ai/catalog.json`: private catalog, selected fixed DeepSeek offering,
  local-source tools and optional labeled foreground web search. Other real model
  entries remain disabled. The model identifier was checked on the public
  [OpenRouter model page](https://openrouter.ai/deepseek/deepseek-v4.1-flash-1017/).
- `.secrets/ai/openrouter.key`: the pre-existing key, unchanged and not displayed.
- `.secrets/ai/master-keys.json`: a newly generated encryption keyring for personal
  credentials. Back it up securely **separately from PostgreSQL**; losing it makes
  stored personal credentials unreadable. These files are ignored and mode 600.
- `.local/embedding-model`: the two pinned, checksum-verified local E5 artifacts,
  ignored by Git and mounted read-only. Runtime inference needs no remote embedding API.
- `infra/ai-home.sh`: composes the existing home, AI-secret and retrieval profiles
  with the explicit `docker-compose.ai-runtime.yml` activation overlay. API and AI
  document consumers use the non-root owner's UID/GID to read mode-600 bind mounts.
  Other workers/Beat/migrations do not receive AI credential mounts.

The activation overlay enables chat, confirmed actions, maintenance, local indexing
and the operator review gate. User reviews remain off until configured explicitly
in AI settings. `UKLADEN_AI_REVIEWS_ENABLED=false` disables that operator gate.
Using this script for `config` or `build` does not start services or call a provider.
Do not use a bare base Compose command later: it omits these AI profiles/settings.

## Owner launch steps

Preparation already created and checked a private database dump, then ran the migration
service with AI flags forced off. PostgreSQL is running; the AI application/services
have not been started. For initial launch, run `up` below. Before later upgrades, make
a fresh backup first. Run from the repository root as the owner of `.secrets/ai`:

```bash
./infra/ai-home.sh                         # quiet configuration validation only
./infra/ai-home.sh backup                  # starts PostgreSQL only; creates a private dump
./infra/ai-home.sh up --detach --wait --wait-timeout 300
./infra/ai-home.sh ps
```

The images were built during preparation. After later code changes, use
`./infra/ai-home.sh build` before `up`. Startup runs the existing migration service
before API/workers. Keep the successful dump and a separate encryption-key backup.
No application data volumes are deleted by these commands.

Open `https://ukladen.app`, sign in, create a new AI chat and select the application
model. Alternatively add a personal OpenRouter key in AI settings and explicitly
select it for a new chat. Never paste keys into chat messages. Try a short synthetic
question first, then source retrieval and a confirmed action. Initial semantic
indexing runs asynchronously; incomplete evidence must remain visible until ready.
Set work windows for planning; reviews additionally require a model and schedule
in AI settings. These user actions consume their selected provider credential.

This preparation does not authorize a coding agent to run live probes or spend the
USD 5 itself. Agent-driven requests still need the bounded operation specified by
`AGENTS.md`. UI instructions are not a guarantee of live model quality.

## Verification

2026-10-29 preparation checks:

- All Docker images built successfully through the prepared home profiles.
- The real pinned local embedding artifacts passed checksum verification and a
  synthetic normalized 384-dimensional query with Docker networking disabled.
- Non-root consumers could access private file metadata and validate the catalog;
  the existing inference key was not read to test setup or sent to a provider.
- Base home and prepared Compose models validated quietly. Assertions checked no
  host ports, AI-secret mounts only on the two consumers, migration isolation and
  both enabled/disabled operator review-gate configurations.
- Shell syntax, backend Ruff/format and Pyright passed. The targeted fake-only
  adapter/access/deployment suite passed 32 tests, including HTTP 402 without retry
  or payer switching and private/failed backup behavior. All 188 browser tests,
  frontend lint/typecheck and production build passed.
- A mode-600 PostgreSQL archive was created before migration; `pg_restore --list`
  accepted it. The migration service completed with all AI flags forced off.

Earlier full backend regression evidence remains in [AI-12](ai-12.md); that full
suite was not rerun for this configuration/UI-copy preparation. The provider cap is
owner-reported, not independently verified. No inference, metered search, management
API call or live model-quality check was made.


### 2026-10-29 streaming diagnostic follow-up

After the owner started the prepared stack, a failed calendar question was traced
to the provider adapter before tool execution. The JSON-sized response limit
interrupted valid SSE streams; a repeated finish marker in a terminal usage choice
was also rejected. The adapter now bounds SSE separately and accepts only empty
usage trailers, while preserving failure on additional content. Truncated/refused
streams remain failures and retain terminal token counts when reported.

Two separately approved operations allowed two and six model calls respectively,
all eight used with retries disabled and explicit route-price ceilings. Only
synthetic questions, schemas and synthetic calendar events were sent to the
selected DeepSeek model; no owner documents/calendar data, web searches or actions
were used. The final framework run read two synthetic calendar events and returned
their correct date and times. Some interrupted attempts did not report usage/cost;
this evidence does not establish a complete actual-spend total. No further agent
provider calls are authorized by that exhausted allowance.

This is narrow live calendar/stream verification, not acceptance of the complete
AI module. Live RAG quality, public search, confirmed actions and proactive reviews
still require their own bounded acceptance checks. Earlier preparation evidence
above describes that earlier operation, not these later diagnostic requests.

The API image was rebuilt and only `api` was recreated with the existing runtime
configuration. Its container became healthy; the local readiness endpoint returned
HTTP 200 and the installed SSE limit was confirmed as 2097152 bytes. No provider
request was made after deployment because the approved diagnostic allowance was
exhausted. Workers and other application services were not recreated.

Verification for this fix: the complete backend suite passed 2084 tests against
isolated PostgreSQL, Redis and object storage with provider access unavailable.
The focused adapter/accounting suite passed 50 tests; backend Ruff/format and
Pyright passed. Base and prepared home Compose configuration validation and
`git diff --check` passed. Frontend checks were not rerun: no frontend code changed.
