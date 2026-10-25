# AI model catalog and API connections

Updated: 2026-10-25.
Status: AI-02 backend implementation, disabled by default. Activation and a live
account smoke remain unverified. No application migration or real model request
has been performed. [AI-01](ai-api.md) supplies chats, execution and retention;
the [product specification](../product/ai.md) owns the full assistant scope.

## Supported integration and dependency boundary

OpenRouter is the first supported adapter. The operator configures explicit,
versioned model offerings; browser requests cannot provide endpoints or model IDs.
The checked-in [example catalog](../../infra/ai-catalog.example.json) includes
the public default `deepseek/deepseek-v4.1-flash-1017`, visible but disabled Claude
Haiku, Claude Sonnet and GPT-5.5 profiles, and a hidden disabled optional text-chat
profile `qwen/qwen3-4b:free`. The latter advertises neither tools nor structured
output. The example does not enable the API or configure a credential.
Free availability, account access and privacy-compatible routes
are activation checks, not guarantees.

Official contracts checked on 2026-10-24:
[DeepSeek](https://openrouter.ai/deepseek/deepseek-v4.1-flash),
[Qwen free](https://openrouter.ai/qwen/qwen3-4b:free),
[model metadata](https://openrouter.ai/api/v1/models),
[routing](https://openrouter.ai/docs/guides/routing/provider-selection),
[limits](https://openrouter.ai/docs/api/reference/limits),
[structured output](https://openrouter.ai/docs/guides/features/structured-outputs),
[streaming](https://openrouter.ai/docs/api_reference/streaming) and
[LangChain integration](https://reference.langchain.com/python/langchain-openrouter/chat_models/ChatOpenRouter).
These public checks did not authenticate an account or prove a real generation.

On 2026-10-25 the owner selected
[DeepSeek V4.1 Flash 1017](https://openrouter.ai/deepseek/deepseek-v4.1-flash-1017).
Its public model ID was checked and the disabled example profile initially advanced
to version 3. The subsequent application-default delivery below advances it to
version 4. Existing private catalogs are not rewritten, and activation or live
tool/JSON/stream compatibility is unverified.

`AgentRunner`, `ModelOffering`, `ModelSelection` and the connection configuration
port remain neutral. The existing LangChain runner/checkpointer is reused; its
historical `OfflineAgentRunner` / `owned_offline_runner` names remain internal.
Real chats register no synthetic tools. Tool-capable offerings now register
[AI-03 authorized reads](ai-03.md); text-only offerings expose no workspace tools.
[AI-04](ai-04.md) now implements streaming chat and settings UI. The adapter's synchronous and streaming protocols are
tested with synthetic HTTP/SSE; async calls reuse the guarded synchronous transport.

Pinned additions: langchain-openrouter 0.2.8, openrouter 0.11.46 and transitive
jsonpath-python 1.1.6. Cryptography 50.0.2 was already installed transitively and is
now directly declared for AES-GCM. The official connector avoids a second model/tool
loop and supplies tool/JSON conversion; its SDK introduces protocol/schema maintenance
and requires Pydantic 2.12.5 / pydantic-core 2.41.5, replacing 2.13.5 / 2.46.5.
Python and existing LangChain pins are unchanged.

## Catalog, model selection and access

`AI_CONNECTIONS_FILE` is an optional API-process path to a private deployment catalog.
Without it the existing fake API works without secret files; no real offering is
available. No file is read during startup, migration or maintenance. Catalog changes
are read on subsequent operations; replace files atomically across all API replicas.

Each entry has an ID, positive version, label, exact provider/model, enabled state,
capabilities and request/input/output bounds. max_input_bytes bounds the entire
serialized request, including tool schemas, from 256 to 65536 bytes (default 6000).
The default tool-capable example uses version 4 and 65536 bytes to fit AI-03 schemas
and bounded evidence; existing private catalogs need an explicit version/budget review. `public: true` makes an enabled entry
available to authenticated completed accounts; otherwise `allowed_user_ids` is the
explicit owner UUID allowlist. Restrictions apply equally to operator and personal
keys. No administrator role, paid subscription or billing UI is introduced.
Disabled entries are hidden unless `listed: true`; listed disabled entries are
returned as unavailable choices. Unknown and unauthorized entries remain hidden.
Disabled/unauthorized models still return 404 when selected, including with a personal key.

`GET /models` adds `available`, `operator_available` and `is_default` to safe model
metadata. `operator_available` checks the local credential's format and permissions,
not provider acceptance, credits or network reachability. There is at most one
`is_default` entry per catalog. The UI preselects it with the application's connection;
missing credentials block creation rather than selecting demo/personal credentials.
An omitted model selects the caller-visible configured default on the server too.
With no configured default the historical fake API behavior remains available.
Explicit `demo: true` creates a fake chat and cannot include a model or connection.

`operator_key_file` names a `.key` file in the catalog directory. It never appears
in public metadata. A personal connection is an owner's OpenRouter API key, usable
only with permitted offerings whose `personal_allowed` is true. Missing operator
keys never fall back to personal keys, or conversely.

Creating a chat accepts optional `offering_id` and `connection_id`. Omission uses
the configured application default, or fake mode when no default is configured;
a connection without an offering is invalid.
Chats retain offering ID/version, provider/model and connection source. Every run
copies that selection. Model, offering revision or connection changes require a
new chat; there is no model-switch endpoint or implicit history transfer. Changing
a catalog model without bumping its version also makes old chats unavailable.
Bump versions when changing a profile's capabilities, payer reference or bounds.
Rotating the contents of the same operator key file preserves the logical account.

Admission and each model dispatch revalidate the active owner, chat/run state,
deadline, catalog access/revision/model and connection. Removing access, disabling
an entry, disconnecting or removing a secret prevents subsequent dispatch.
No model-network discovery or credential validation runs automatically.

## HTTP additions

All paths are relative to `/api/v1/ai`, require the existing active,
completed-registration session and return `Cache-Control: no-store`. Mutations
require allowed Origin and CSRF. Owner identity is never accepted in a body.

| Method / path | Contract |
| --- | --- |
| GET /models | Authorized enabled or explicitly listed safe profiles, availability and default flags; no credentials, paths or owner allowlists |
| GET /access | Current owner's plan and nullable monthly request/token limits; currently free with no product quotas |
| POST /connections | `{label, key}`; stores an encrypted OpenRouter credential without a network call; 201 masked metadata |
| GET /connections | Up to 20 retained owned connection records, including disconnect state |
| DELETE /connections/{id} | 204; erase ciphertext/key identifier, persist disconnect time and cancel unfinished runs on that connection; repeated disconnect is safe |
| POST /connections/{id}/rotate | 204; re-encrypt an active owned connection with the current master key, without a provider call |
| POST /conversations | Title plus optional offering_id/connection_id or explicit demo; application default if configured; immutable model selection |

Connection metadata is limited to id, label, creation/disconnect times and the fixed
mask `********`. Keys are printable ASCII, 16–1024 characters; labels are trimmed,
nonblank and at most 100 characters. At most 20 connection records are retained per
owner, including tombstones. Missing/foreign connections return 404. Configuration,
secret or decryption failures return sanitized 503; invalid bodies return 422.
Connection/profile IDs and credential source are added to chat/run responses.
No endpoint returns ciphertext, master-key identifiers, provider response bodies
or unmasked credentials. There is no credential replacement endpoint: connect a new
key and start a new chat, then disconnect the old key.

Revision `0024_ai_connections` adds encrypted connections, quota buckets and chat/run
selection columns. Composite owner foreign keys prevent foreign connection references.
Existing chats are backfilled as fake/fake-v1. Downgrade refuses retained connections
or real selections instead of dropping them. It is tested on disposable databases;
deploying it to the application is a separate operation.

## Limits, failures and usage

The existing 60-second run, four-attempt and eight-tool ceilings remain. The real
SDK has retries disabled; real network/provider errors are not automatically retried.
The API does not sleep on 429/503. It persists Retry-After (delta or HTTP date), capped
at 24 hours, with a 60-second default, and denies new dispatch until eligible.
The model/credential never switches implicitly. The request disables OpenRouter
provider failover, requires parameter support, excludes data-collection routes and
enables no hosted plugins. This privacy policy can make a free offering unavailable.

An atomic PostgreSQL fixed window counts at most `requests_per_minute` attempts per
connection. Operator offerings sharing a secret file share the counter; personal
connections use their own owner-bound ID. Limits are shared across API processes,
survive restart and fail closed if persistence is unavailable. Invalid/failed attempts
may conservatively consume quota. Provider/account limits may be lower.
The request body is additionally bounded to 6000 UTF-8 bytes including protocol/tool
schema overhead, and output to 2048 tokens. The byte bound is deliberately stricter
than the planned input-token budget; this adapter does not claim an exact DeepSeek
tokenizer count. Oversized history is rejected rather than silently truncated.
Transport connect/read timeouts and a 128 KiB response/60-second stream bound complement
the existing process-wide eight-slot execution pool and late-result barriers.

Refusal, invalid tool JSON, unsupported modes, interrupted streams and truncation
cannot become actions or completed answers. Tools and structured output use separate
requests. Stream fragments only become complete framework arguments after assembly;
the HTTP chat endpoint still returns a stored result, not live SSE. Provider reasoning
and raw response metadata are removed before checkpointing.

Reported input/output token counts, including measured zero, enter the existing
attempt ledger. Missing counts remain unknown independently. Schema-invalid responses
preserve safely parsed partial usage. Refused/truncated results retain reported usage.
Usage arriving after cancellation updates an existing unexpired interrupted attempt
without reopening it, saving an answer or extending retention. No detailed usage is
recreated after cleanup. This stage implements neither invoices nor monetary budget
reservations; use OpenRouter account/key limits before enabling paid traffic.
`free_only` also sends zero maximum prompt/completion/request prices and never falls back to
a paid model. Live prices, quotas and account processing/retention terms must be
checked for the selected account; local totals do not represent its external traffic.

## Local provisioning, rotation and backups

### Application key and developer-managed models

The owner confirmed on 2026-10-25 that ordinary users must not need API keys.
Copy the reviewed example to the private catalog when provisioning; DeepSeek is the
public application default. Put the owner's **OpenRouter** key in the single private
file `.secrets/ai/openrouter.key`, referenced by `operator_key_file`. Never put this
shared credential in a personal connection or browser code. The API container runs
as UID 10001, which must be able to traverse/read the private directory/files.
The encryption keyring is needed only for optional personal connections, not the
application key. Keep the API flag disabled until migrations and deployment setup
are complete; no private file, real environment, application DB or deployment is
changed by this delivery.

To offer another model later, edit the private catalog: verify the exact model ID,
capabilities, account access and privacy-compatible route, set its credential
reference, bump its version and set `enabled: true`. `listed: true` keeps a disabled
profile visible as "not yet available". Only one profile may have `is_default: true`.
The confirmed public IDs for the disabled examples were checked on 2026-10-25:
[Haiku](https://openrouter.ai/anthropic/claude-haiku-5.5),
[Sonnet](https://openrouter.ai/anthropic/claude-sonnet-5.5),
[GPT-5.5](https://openrouter.ai/openai/gpt-5.5).
They remain unverified for live tools/JSON/streaming; no request is sent merely to
list a model. Supporting a different provider adapter still requires implementation.

### Future user quotas

`AiAccessPolicy` is the application boundary for future user entitlements. Its
current `UnlimitedAiAccessPolicy` reports plan `free` and null monthly request/token
limits and imposes no product quota or payment gate. The owner-only usage ledger
continues to count runs, provider attempts and known/unknown tokens, including use
of a shared application key. Technical connection throttles, execution/size bounds
and upstream account limits remain separate and unchanged.

The policy admission hook runs for a new submission inside the existing serialized
owner transaction, before its run/message is stored. Exact retries reuse the stored
run and do not reserve quota again. A future policy can reject with `UsageLimited`
(HTTP 429) or reserve quota atomically using the transaction repository. Subscription
storage, quota counters/reservations, reset periods, token settlement and payments
are **not implemented**. A future quota implementation must add authoritative,
race-safe persistence through Alembic and cannot use the 30-day display report as a
durable billing counter. No migration or new user plan assignment is needed now.

### Personal connections, rotation and backups

Private runtime files belong in `.secrets/ai/`, ignored by Git. The optional
`docker-compose.ai.yml` mounts that directory read-only into **api only**; workers,
Beat, migration and extraction processes receive no mount. It does not enable AI,
change real environment files or apply migrations. Host API use instead sets
`AI_CONNECTIONS_FILE` to the private catalog's absolute path. Keep keys out of shared
`.env` files, terminal arguments and chat messages.

Before creating private files, verify the ignore rules:

~~~bash
git check-ignore .secrets/ai/catalog.json .secrets/ai/openrouter.key .secrets/ai/master-keys.json
~~~

Create the directory with mode 700. Copy the example to `catalog.json` only if the
destination does not exist. Store the operator key in `openrouter.key` using a local
secret editor, with mode 600. Never overwrite an existing keyring. Its JSON shape is
`{"active":"v1","keys":{"v1":"<base64-encoded random 32-byte key>"}}`.
Generate the bytes with `os.urandom(32)` or a cryptographic secret manager; store them
directly in a mode-600 file without printing. Keep at most eight keys in the ring.
Secret files must be regular non-symlink files without group/other permissions.

Personal keys use AES-256-GCM with a fresh 12-byte nonce and associated data binding
format version, provider, owner UUID and connection UUID. PostgreSQL contains only
ciphertext/nonce and its encryption-key ID. The deployment-managed master key is
outside PostgreSQL. Swapping owners/connection IDs, tampering, missing keys or a
broken keyring prevents decryption; no plaintext fallback exists.

For rotation, atomically add a new key and make it active, retaining old keys for
reads. Call the authenticated rotate endpoint for each retained active connection;
it decrypts and re-encrypts under the existing owner lock. Verify all active rows use
the new ID before retiring an old key. Back up DB ciphertext and keyring separately
with access controls. Restore needs the matching keys. Losing keys makes credentials
unrecoverable and requires reconnection. Old backups can contain disconnected keys:
restore with AI disabled, revoke compromised keys at OpenRouter, reconcile subsequent
disconnects and review active connections before resuming. Restoring a DB alone is
not evidence that an old credential is still authorized.

## Activation and synthetic account smoke

Keep AI disabled until the reviewed migrations are applied to the intended target,
maintenance is enabled and connection/privacy/account limits have been checked.
The current owner's UUID is available from authenticated `GET /api/v1/users/me`;
it belongs in private configuration, not the checked-in example.
Enable only reviewed profiles. The current owner-selected default DeepSeek profile
is public to completed authenticated accounts; private/restricted profiles still
require explicit UUID allowlists. Never widen a restricted profile to bypass setup.
The free example can be offered publicly after verifying its current route and quotas.

Validate without exposing resolved secrets:

~~~bash
docker compose config --quiet
docker compose -f docker-compose.yml -f docker-compose.ai.yml config --quiet
docker compose --env-file .env.home -f docker-compose.yml -f docker-compose.home.yml -f docker-compose.ai.yml config --quiet
~~~

After explicit activation, use an authenticated owner session to list models, add a
personal key if desired, and create a new selected chat. Submit one fixed synthetic
message, inspect stored attempt/usage status and disconnect the test connection.
Private pages/files are not probes. Use separate synthetic tool/JSON/stream checks
before promoting those capabilities for an account. Simulate failures offline rather
than deliberately exhausting real quotas. No live account smoke has run in this slice.

Rollback: disable affected catalog entries or AI_ENABLED, retaining maintenance for
migrated data. Disconnect personal keys or remove operator secret access. Preserve
existing chats, business objects, data volumes and encryption backups; do not force
a destructive migration downgrade. UI/model settings are delivered in [AI-04](ai-04.md).

## Verification (2026-10-24)

The final full backend suite passed **1696 tests / 3 skipped** in 357.09 seconds,
with AI_TEST_DATABASE_URL and AUTH_TEST_DATABASE_URL pointing only to disposable
PostgreSQL 18 and AUTH_TEST_REDIS_URL pointing to disposable Redis. The three skips
require a disposable S3 target. Services ran in a network-isolated namespace with
RAM-only data and read-only code/runtime mounts. No AI/auth test schemas remained;
both temporary service containers were removed after the run.

Full Ruff, format check and Pyright passed. Lockfile/installed-dependency checks, base/AI/home
quiet Compose validation, API-only secret-mount/home exposure assertions, disabled
example-catalog validation, private-file ignore checks, 263 local Markdown links
across 12 changed documents, a network-disabled Gitleaks scan of the staged diff
(no leaks) and git diff --check passed. The first full run found an
outdated expected migration-head assertion; it was corrected before the successful
final full run. The post-interruption repeat saved its output outside the repository.

No real credential, application environment, application migration, provider generation,
frontend change, push or deployment was performed. Live account model/capability,
quota, price and retention checks remain activation gates. Frontend and native S3
checks were not run for this backend-only slice.
