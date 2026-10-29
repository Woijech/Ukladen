# AI diagnostics operator guide

Status: implemented locally. Deployment and real-model acceptance are separate
operations. This feature does not activate providers or authorize agent spending.

## Access and installation

The panel lives at /workspace/ai?tab=diagnostics, inside the existing AI screen.
AI_DIAGNOSTIC_ADMIN_IDS is a JSON array of authenticated user UUIDs. Empty by
default, it denies access. This is a narrow operator grant, not a general admin
role: operators can inspect and execute only their own normal authorized AI data.

1. Sign in with the account used for testing. Read the id field from the existing
   authenticated /api/v1/users/me endpoint. After installing this feature, the
   closed diagnostics page also shows your UUID, as does its /access endpoint.
   Do not infer identity from the last run.
2. Add this setting to the private .env.home, replacing the example UUID:

       AI_DIAGNOSTIC_ADMIN_IDS='["11111111-2222-4333-8444-555555555555"]'

   Add other explicitly trusted UUIDs to the array if necessary. Each sees only
   its own data. No API keys belong in this setting.
3. Build, back up, migrate and recreate the changed consumers:

       ./infra/ai-home.sh build api worker web
       ./infra/ai-home.sh backup
       ./infra/ai-home.sh run --rm --no-deps migrate
       ./infra/ai-home.sh up --detach --no-deps --wait --wait-timeout 120 api worker web

   The wrapper invokes Docker Compose with the existing home/AI/retrieval overlays.
   Migration has real AI flags disabled. API retains its current activation settings;
   the ordinary worker has provider access disabled and supplies retention cleanup.
   These commands do not request inference; existing user requests and configured
   background jobs retain their behavior. Do not enable new provider/review flags
   merely to install diagnostics.
4. Reload AI. Granted accounts see Diagnostics. If missing, verify the UUID, JSON
   syntax, selected .env.home and API recreation.
5. Revoke by removing the UUID and recreating API. Future runs no longer capture
   content. Existing captures follow their retention/deletion policy.

Revision 0041_ai_diagnostics adds owned chat opt-in and capture/review records.
It preserves existing chats, runs, credentials and business content. Downgrade
refuses to discard retained capture/review rows. Delete them explicitly first;
use the backup rather than deleting application data volumes.

## First test without a provider

1. Leave "Check mechanism without API" selected and click Create test chat.
2. The model defaults to Demonstration, even when a paid default model exists.
   Read the capture notice and create the chat. Creation never calls a model.
3. The scenario question is prefilled. Send it manually.
4. Expect the scripted fake_double tool with input 7 and final result 14.
5. Return to Diagnostics, refresh and open the run. Inspect the timeline, model
   requests/responses and tool arguments/result. Record a Passed review with why.
6. Download the JSON report if needed. Delete the capture or test chat afterwards.

A passed demonstration proves the local mechanism, not DeepSeek quality or RAG.

## Live testing

Each real-model message uses the selected application or personal credential and
may incur costs. One message can make multiple bounded model calls. Diagnostics
has no automatic live batch button. Normal limits, cancellation, permissions and
exact action confirmation remain in force; the panel adds no spending cap.
Coding agents still need the bounded approval in AGENTS.md for any live probe.

Prepare recognizable synthetic content through ordinary UI:

- A private "QA: statistics" page with a short definition and distinctive fact.
- A small TXT/PDF containing a known sentence. Wait for extraction/index readiness.
- A personal event tomorrow with known title/times; check profile timezone first.
- Use the QA prefix for test tasks and clean them up manually after confirmation.

Use a new chat per model, credential and scenario so history does not contaminate
comparisons. Deliberately switch from Demonstration to the desired real model.
Live tools read the account's normal data: the panel does not inject a fake
calendar into a real account. Use a dedicated QA account for stronger separation.

| Scenario | Preparation | Required observation |
| --- | --- | --- |
| Tomorrow calendar | Known event/schedule, correct timezone | Calendar tool, correct date range, answer matches events |
| Document explanation | Select only the test page/material | Retrieved fragments support the answer and citations |
| Missing fact | Ask about unavailable private grades | Honest unavailability; no fabricated grades or schedule |
| Confirmed task | Ask for a QA task | Proposal only before confirmation, exactly one task after |
| Cancellation | Start a run and Stop | Terminal cancellation; no later answer or applied action |
| Provider failure | Fake transport tests or an existing failure | Safe error/status, no invented usage or payer switch |
| Source change | Edit the page between separate runs | Current content/version; old citations remain historical |
| Restricted sources | Select one source | Reads respect scope and ownership |

Web fallback follows the normal catalog policy and source-only setting. For a
local-only test, use the chat's source-only control. Diagnostic mode itself does
not enable or disable web tools. A confirmed action uses normal real services;
diagnostic mode is not a write sandbox. Never confirm writes just to test reading.

## How to investigate

Inspect the timeline, then expand content in chronological order:

- No model attempt: check activation, admission, selected connection and limits.
- Model failed before tools: inspect provider_failure. HTTP status is shown when
  exposed by the SDK; a static stream reason identifies the protocol stage.
  Unknown price does not itself mean provider failure.
- Answer without a necessary tool: inspect model context and available tools.
- Wrong dates: compare arguments with current date and profile timezone.
- Empty/partial tool result: check normal source UI, extraction/index and warnings.
- Correct evidence, incorrect answer: record an answer-quality failure.
- Missing tokens: preserve Unknown; do not replace missing counts with zero.
- Interrupted/cancelled: use normal chat recovery/Stop. Opening or refreshing
  diagnostics does not resume or repeat a provider request.

The Usage tab supplies date/model/payer token and estimated-cost summaries,
including demo activity and unknown accounting. Manual Passed/Failed reviews
are operator judgments, not authenticity checks or automatic release gates.
Record expected fact, actual tool/source result and the reason for the verdict.

## Capture, retention and exports

Ordinary runs keep their existing content-free attempt/tool journal. Detailed
capture applies only to new chats explicitly created through Diagnostics, while
their owner has the server grant. It is not retroactive.

Capture includes bounded framework-visible model messages/system context, tool
names, assembled arguments/results and safe provider failures. It excludes HTTP
headers/credentials, raw upstream error bodies, checkpoints and hidden reasoning.
Structured sensitive fields, JSON tool results and recognizable sk-/Bearer strings
are redacted. This is not a universal secret detector: arbitrary secrets in prose
cannot reliably be recognized. Never put credentials in test content.

Each event is bounded to 16 KiB; oversized events show a shortened preview. Each
run is bounded to 64 events / approximately 240 KB, with database enforcement at
256 KiB. Truncation is visible. Captures and manual reviews expire seven days after
run creation and are immediately hidden at expiry. The existing retention worker
physically purges bounded batches. Stop a run before clearing its capture.
Deleting its chat immediately cascades captures and opt-in. Normal journal
retention remains 30 days. Delete the test chat to stop capture for future turns.

Detailed content capture covers normal foreground chat model/tool execution.
Durable full-source document steps and scheduled reviews keep existing accounting
but do not gain detailed capture here. Use normal source inspection, citations and
document progress for background paths.

JSON export is a local browser download of the selected run, capture and review.
It can include private excerpts: inspect/redact before sharing. Export does not
upload anything, call a model or reveal another account's data.

## Repeatable acceptance and developer checks

The [AI-09 suite](ai-09.md#synthetic-suite-and-review-tool) contains 40 versioned
acceptance scenarios. Five panel presets are starting points, not a replacement.
Its scoring command evaluates supplied human reviews and never executes models.
Panel JSON exports are diagnostic records, not directly compatible AI-09 review
files; use the documented AI-09 review template for that separate quality gate.
A live record needs exact model/fixture revision, observed outcomes, actual usage
and reviewer rationale. Unit tests alone cannot establish model-answer quality.

Use disposable PostgreSQL/Redis/object storage and fake transports for backend
Ruff/format, Pyright and pytest. Run frontend lint/typecheck/build/Playwright and
Compose validation. Never point tests at the home database or consume provider
quotas merely to check setup. Security regressions cover default denial, CSRF,
cross-owner access, capture/replay, review, redaction, bounds, retention and cascade.
Browser regressions cover access denial, demo-first creation without automatic
inference, safe rendering, review, export and clearing.

## Verification on 2026-10-29

- The initial full backend run finished with 2087 passed and two failures from the
  same imported migration round-trip test: its explicit table inventory omitted
  the two new diagnostic tables. That inventory was updated. The final affected
  migration/diagnostics/retention/provider/accounting suite passed all 82 tests,
  including both round-trips, ORM schema comparison and refusal to discard retained
  capture on downgrade. The complete suite was not repeated after this test-only
  inventory correction and the final targeted capture expiry/read checks.
- All 193 browser tests passed on the final UI, including source-only payloads,
  operator denial, demo-first explicit execution, capture/review/export, safe
  rendering and desktop/mobile layout. Final screenshots were visually inspected.
- Backend Ruff and format passed (556 files); Pyright reported zero errors.
  Frontend lint, typecheck and production build passed. The local sandbox prevented
  Next's TypeScript subprocess output parsing; the normal-permission production
  build passed without changing dependencies or suppressing type checks.
- Base and prepared home Compose models validated quietly. API, ordinary worker
  and web Docker images built successfully. Shell syntax and diff checks passed.
- All provider execution in this feature's verification used fakes and synthetic
  credentials, with native backend services on an isolated internal network. No
  real inference, search or embedding-provider quota was consumed.
- No operator UUID was inferred/granted, no home database migration was applied,
  and no running application service was recreated for this feature. Follow the
  installation section to enable the selected account and install the built images.
