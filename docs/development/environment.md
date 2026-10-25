# Environment configuration

Status: implemented configuration reference, audited 2026-10-21; AI connection settings
updated 2026-10-24. The source of truth
is `apps/backend/src/app/core/config.py`, Compose and `apps/web/next.config.ts`.
The fake default and optional OpenRouter connection-file settings below are implemented.

## Loading and precedence

| Process | Configuration source |
| --- | --- |
| Host API, Alembic, workers, Beat | Run from `apps/backend` with `uv run --env-file ../../.env …`. Pydantic also reads `.env` in the process working directory. Existing process environment wins. |
| Base Compose | Root `.env` supplies interpolation and the backend `env_file`. Explicit service `environment` replaces `DATABASE_URL`, `REDIS_URL` and `S3_ENDPOINT` with internal addresses. |
| Home Compose | Always pass `--env-file .env.home -f docker-compose.yml -f docker-compose.home.yml`. The overlay replaces, rather than appends to, backend `env_file`. It reuses the same data volumes. |
| Host Next.js | Process environment and Next.js env files under `apps/web`; the root backend `.env` is not loaded by Next.js. |
| Docker Next.js | Dockerfile sets build argument `BACKEND_URL=http://api:8000`. The rewrite is captured at build time; changing runtime ENV does not rewrite a built server. |
| CI | Synthetic PostgreSQL/Redis/S3 test settings in `.github/workflows/ci.yml`. No real SMTP, Google, IIS account or AI credentials. |

Do not create a second real backend `.env` under `apps/backend`. Do not `source` an
untrusted env file. Copy examples only when the destination does not exist; compare
new examples with existing private files and move required values manually.

Optional settings must be **omitted**, not assigned an empty value. Pydantic does
not treat an empty string as `None`: empty URLs, numeric values and optional secrets
fail validation. The intentionally blank mandatory credentials in `.env.home.example`
must be filled before use. JSON arrays such as origins should be enclosed in single
quotes in dotenv files. Quote secrets containing `#`, spaces or `$` according to
Compose dotenv rules; do not paste them into commands or diagnostic output.

Unknown backend keys are ignored because the same env file also contains Compose
settings. A misspelled optional name can therefore leave its default active. Use the
exact names below. Validation errors hide input values; never print resolved settings,
`docker inspect`, or full `docker compose config` for private files. Use `config --quiet`.

## Application, database and Redis

| Variable | Default / required | Format, source and behavior |
| --- | --- | --- |
| `POSTGRES_DB` | Required by Compose; example `ukladen` | Database name, also used in its assembled DSN. Initialization only when the volume is empty. |
| `POSTGRES_USER` | Required by Compose | Database role. Preserve existing credentials for existing volumes. |
| `POSTGRES_PASSWORD` | Required, nonempty in Compose | Operator-chosen secret. Changing ENV does not rotate a password inside an existing database. |
| `POSTGRES_HOST_PORT` | `5432`, base Compose only | Free host TCP port. Containers always use `postgres:5432`; update the port in the host `DATABASE_URL` separately. Home publishes no database port. |
| `DATABASE_URL` | Required by backend/Alembic | `postgresql+psycopg://user:password@host:port/database`. Only the installed synchronous Psycopg driver is accepted. Host example uses localhost; Compose constructs the internal URL. |
| `REDIS_URL` | Required by backend/workers/Beat | `redis://[user:password@]host:port/db` or `rediss://…` for TLS. Host example uses database 0. Compose supplies `redis://redis:6379/0`. |

Compose inserts PostgreSQL components into a URL without percent-encoding. Use
URL-safe credentials/components for that deployment (a generated hexadecimal secret
is suitable). A manually supplied host DSN must percent-encode reserved characters.
Never copy production connection URLs into test variables.

There is no `APP_ENV`, `DEBUG`, separate `CELERY_BROKER_URL`, Celery result backend,
or `DATABASE_TEST_URL` setting. Celery shares `REDIS_URL` with auth cache, rate limits,
OAuth state and synchronization locks. Redis is disposable; PostgreSQL remains
canonical. Queue loss can lose auth email; reminders/materials recover via database
scans. Beat intervals and worker concurrency are defined in code/Compose, not ENV:
reminders/material maintenance every 30 seconds, selected-group scans every 60 seconds,
normal worker concurrency 2, material worker concurrency 1. Run exactly one Beat.

## Authentication

All durations are positive integer seconds. Password length is a character count.
These values are consumed by API application services and cookie helpers; token
lifetimes also inform worker email text. Keep backend process settings consistent.

| Variable | Application default | Meaning |
| --- | --- | --- |
| `AUTH_SESSION_TTL_SECONDS` | `2592000` | Session and session-cookie lifetime, 30 days. |
| `AUTH_PASSWORD_MIN_LENGTH` | `12` | Password minimum, allowed range 1–1024; maximum accepted length is always 1024. Browser registration/reset forms use a 12-character minimum; completion reads server policy. Keep 12 unless deliberately adapting the UI too. |
| `AUTH_EMAIL_VERIFICATION_TTL_SECONDS` | `86400` | Verification token lifetime. |
| `AUTH_PASSWORD_RESET_TTL_SECONDS` | `3600` | Password recovery token lifetime. |
| `AUTH_SESSION_COOKIE_NAME` | `__Host-ukladen_session` | Opaque HttpOnly session cookie. |
| `AUTH_CSRF_COOKIE_NAME` | `__Host-ukladen_csrf` | CSRF bootstrap cookie; mutations also need the header and allowed Origin. |
| `AUTH_OAUTH_COOKIE_NAME` | `__Host-ukladen_oauth` | Browser binding for Google flows. |
| `AUTH_COOKIE_SECURE` | `true` | Required with `__Host-`/`__Secure-` names. Local HTTP example explicitly uses false and unprefixed names. |
| `AUTH_COOKIE_SAMESITE` | `lax` | `lax` or `strict`; Google browser linking requires `lax` for the cross-site callback. |
| `AUTH_ALLOWED_ORIGINS` | `[]` | JSON array of exact scheme/host/port origins, without credentials/path/query/fragment. Empty denies mutations. Home uses its public HTTPS origin. This is not CORS configuration. |

Cookie names must be distinct valid cookie tokens. Cookies have Path=/ and no Domain.
No JWT signing secret is needed: Ukladen uses opaque sessions, not JWT browser tokens.

Each rate setting below has a corresponding positive `…_RATE_WINDOW_SECONDS`,
default **60**. The limit and window are shared across API replicas through Redis.

| Limit variable | Default | Window variable | Key scope |
| --- | --- | --- | --- |
| `AUTH_LOGIN_RATE_LIMIT` | 10 | `AUTH_LOGIN_RATE_WINDOW_SECONDS` | Peer address and separately normalized email |
| `AUTH_REGISTER_RATE_LIMIT` | 5 | `AUTH_REGISTER_RATE_WINDOW_SECONDS` | Peer address |
| `AUTH_PASSWORD_CHANGE_RATE_LIMIT` | 5 | `AUTH_PASSWORD_CHANGE_RATE_WINDOW_SECONDS` | User |
| `AUTH_EMAIL_VERIFICATION_CONFIRM_RATE_LIMIT` | 5 | `AUTH_EMAIL_VERIFICATION_CONFIRM_RATE_WINDOW_SECONDS` | Peer address |
| `AUTH_EMAIL_VERIFICATION_REQUEST_RATE_LIMIT` | 5 | `AUTH_EMAIL_VERIFICATION_REQUEST_RATE_WINDOW_SECONDS` | User |
| `AUTH_PASSWORD_RESET_CONFIRM_RATE_LIMIT` | 5 | `AUTH_PASSWORD_RESET_CONFIRM_RATE_WINDOW_SECONDS` | Peer address |
| `AUTH_PASSWORD_RESET_REQUEST_RATE_LIMIT` | 5 | `AUTH_PASSWORD_RESET_REQUEST_RATE_WINDOW_SECONDS` | Peer address and separately normalized email |
| `AUTH_GOOGLE_START_RATE_LIMIT` | 10 | `AUTH_GOOGLE_START_RATE_WINDOW_SECONDS` | Peer address |
| `AUTH_GOOGLE_CALLBACK_RATE_LIMIT` | 10 | `AUTH_GOOGLE_CALLBACK_RATE_WINDOW_SECONDS` | Peer address |
| `AUTH_GOOGLE_LINK_RATE_LIMIT` | 5 | `AUTH_GOOGLE_LINK_RATE_WINDOW_SECONDS` | User |

## Google OAuth

Optional. In Google Cloud Console, configure consent and create an OAuth **Web
application** client. Copy its client ID/secret privately and register the exact
callback URI below in **Authorized redirect URIs**. See [Google setup](google-auth.md)
for account resolution, testing and troubleshooting.

| Variable | Default / required | Meaning |
| --- | --- | --- |
| `GOOGLE_CLIENT_ID` | Unset | Web application client ID, normally ending `.apps.googleusercontent.com`. Not an API key. |
| `GOOGLE_CLIENT_SECRET` | Unset | Secret issued with that client; backend only. |
| `GOOGLE_REDIRECT_URI` | Unset | Exact backend `/api/v1/auth/google/callback` URL registered with Google. |
| `FRONTEND_AUTH_SUCCESS_URL` | Unset | Fixed frontend destination, normally `/workspace`. |
| `FRONTEND_AUTH_ERROR_URL` | Unset | Fixed frontend destination, normally `/auth/error`. |
| `AUTH_OAUTH_STATE_TTL_SECONDS` | `600` | Positive lifetime for browser-bound OAuth state and mailbox challenges. |

The first three must be supplied together or all omitted. Frontend destinations
must be supplied as a pair. Browser Google login needs all five values; partial
browser configuration returns provider unavailable. All URLs must be HTTPS except
loopback development (`localhost`, `127.0.0.1`, `[::1]`), with no credentials/query/
fragment. Local example uses `http://localhost:8080`; home uses `https://ukladen.app`.
Keep destinations on the application's origin. These values never belong in
`NEXT_PUBLIC_*`, browser storage or source code. Omission disables the provider;
the current frontend still shows its button and reports unavailable if selected.

## Email / SMTP

| Variable | Default / required | Meaning |
| --- | --- | --- |
| `AUTH_EMAIL_DELIVERY_MODE` | `disabled` | `disabled`, `fake`, `smtp`. Disabled rejects email-dependent issuance. Fake retains at most 100 messages per worker process, sends nothing and logs no tokens. Use SMTP for usable browser registration/recovery. |
| `AUTH_EMAIL_VERIFICATION_URL` | Unset | `/auth/verify-email` on an allowed frontend origin; HTTPS except loopback. Without it, mail contains a manual token. Reset and Google confirmation links reuse its origin. |
| `SMTP_HOST` | Required in smtp mode | Hostname/IP from the email provider, not a URL; no empty value. |
| `SMTP_PORT` | `587` | Integer 1–65535; usually 587 for STARTTLS or 465 for implicit TLS. |
| `SMTP_SECURITY` | `starttls` | `starttls`, `tls`, `none`. Both TLS modes verify certificates. None is only appropriate for a trusted local receiver. |
| `SMTP_USERNAME` | Unset | Provider login; optional only together with omitted password. |
| `SMTP_PASSWORD` | Unset | Provider password/app password; required when username is supplied. Plaintext SMTP authentication is rejected. |
| `SMTP_FROM_EMAIL` | Required in smtp mode | Verified bare sender address, e.g. `noreply@example.com`; no display-name syntax. Obtain/verify the domain with your provider. |
| `SMTP_TIMEOUT_SECONDS` | `10` | Finite number greater than zero and at most 60; bounds SMTP socket operations. |

API checks configuration and publishes after database commit; the worker delivers.
SMTP credentials are independent of Google OAuth and Cloudflare Tunnel. A queue/SMTP
failure does not roll back an already created account. There is no durable email
outbox; use resend/recovery after restoring delivery. See [email operations](auth-email.md).

## Storage

| Variable | Default / required | Meaning |
| --- | --- | --- |
| `S3_ENDPOINT` | Required | HTTP/HTTPS S3 endpoint. Host: localhost:8333; Compose: seaweedfs:8333. Use TLS for a remote deployment. |
| `S3_ACCESS_KEY` | Required, nonempty | Operator/provider S3 credential. Compose maps it to SeaweedFS `AWS_ACCESS_KEY_ID` and `WEED_ADMIN_USER`. |
| `S3_SECRET_KEY` | Required, nonempty | Matching private secret; Compose maps it to `AWS_SECRET_ACCESS_KEY` and `WEED_ADMIN_PASSWORD`. |
| `S3_BUCKET` | Required, nonempty | Private bucket, `materials` in examples. SeaweedFS mini creates it on startup. Avatars and materials use distinct object prefixes. |

No duplicate AWS/SeaweedFS variables need to be added to `.env`; Compose owns those
translations. The adapter uses region `us-east-1`, path addressing and signed requests.
The readiness probe checks the S3 process, not credentials/bucket permissions. File
limits are code contracts (25 MiB/file, 1 GiB/user), not configurable ENV. PostgreSQL
stores metadata only. Existing objects and credentials must be preserved on upgrade.

## University / Schedule and AI / LLM

| Variable | Default | Meaning |
| --- | --- | --- |
| `SCHEDULE_SYNC_ENABLED` | `true` | Boolean used by API, worker and Beat. False disables accepted/periodic imports; stored calendar reads and reminder/material maintenance continue. |
| `SCHEDULE_SYNC_INTERVAL_SECONDS` | `3600` | Integer 60–86400; selected-group refresh threshold and calendar stale warning threshold. It is not Beat's polling period. |
| `AI_ENABLED` | `false` | Opts in to authenticated chats after reviewed migrations. Explicit selected offerings can call real models; unselected chats stay fake. No startup DDL. |
| `AI_ACTIONS_ENABLED` | `false` | Registers AI-07 proposals and permits exact owner decisions only when AI itself is enabled; requires migration 0031. Does not enable automatic actions or provider spending. |
| `AI_RETENTION_ENABLED` | `false` | Continue migrated recovery/cleanup independently when chat is disabled. |
| `AI_LLM_PROVIDER` | `fake` | Preserves the fake default; real selections come from the catalog rather than a global provider switch. |
| `AI_LLM_MODEL` | `fake-v1` | Only fake-v1 is supported; other values are rejected. |
| `SEARCH_EMBEDDINGS_DIRECTORY` | Omitted | Verified local AI-05 artifact directory; enables AI-06 index scanning/query embeddings. Optional retrieval Compose overlay maps it read-only to `/model` in CPU consumers. No startup download or real provider fallback. |
| `AI_CONNECTIONS_FILE` | Omitted | AI-consumer path to the private deployment catalog. Optional AI Compose overlay mounts `.secrets/ai` into API and the opted-in AI document worker. No plaintext keys in env files. See [connections](ai-connections.md). |

Public IIS uses the adapter's verified public base URL; no IIS password/token or
private account connection is implemented. The [AI API](ai-api.md) preserves synthetic
model/tool responses by default. AI-02 implements optional OpenRouter models and
encrypted personal connections, disabled/unactivated. Embeddings and semantic search
remain unimplemented. Remaining settings in [AI plans](ai-setup.md) do not activate providers.

## Logging, frontend and deployment

| Variable | Source / default | Meaning |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`; application JSON logging in API/workers. DEBUG does not enable raw SQL, request bodies or SDK payload logging. |
| `BACKEND_URL` | Next.js host default `http://localhost:8000` | Server-only API rewrite target. Set before `npm run dev` or production build. Docker build argument defaults to `http://api:8000`; root backend ENV does not configure the web image. |
| `PORT` | Standalone server default `3000` | Host frontend port. Playwright sets 3001 and refuses to reuse an existing server. Docker runtime sets 3000. |
| `HOSTNAME` | npm start / Docker: `0.0.0.0` | Server listen address; Docker host exposure is separately bound to loopback or removed by the home overlay. |
| `CLOUDFLARE_TUNNEL_TOKEN` | Required only for home Compose | Obtain from the remotely managed tunnel's Docker install command. Compose passes it as `TUNNEL_TOKEN` only to cloudflared and blanks it in backend containers. |
| `FORWARDED_ALLOW_IPS` | Home API service: fixed proxy IPs | Uvicorn trust, set by the overlay. Change together with edge network/static addresses and Traefik trust; never set `*` for an exposed API. |

`NODE_ENV=production`, `NEXT_TELEMETRY_DISABLED=1`, `PYTHONUNBUFFERED=1`, uv build
options and image versions are Dockerfile/CI settings, not application knobs.
No public client ENV, Sentry key, metrics endpoint, standalone production profile
or deployment automation is implemented. Follow [home hosting](../deployment/home-server.md).

## Isolated test configuration

The full backend suite needs all the variables below; without services, integration
tests skip. Use a fresh disposable database/Redis/S3 service, never application data.
Fixtures create/drop temporary PostgreSQL schemas; Redis fixtures can flush the
selected logical database. S3 tests create/delete generated objects in the test bucket.

| Variable | Purpose |
| --- | --- |
| `AUTH_TEST_DATABASE_URL` | Synchronous Psycopg DSN for disposable PostgreSQL 18 with pgvector available. |
| `AUTH_TEST_REDIS_URL` | Disposable Redis database, conventionally `/15`. The name covers all modules, not just auth. |
| `AVATAR_TEST_S3_ENDPOINT` | Disposable SeaweedFS endpoint, shared by avatar/material tests. |
| `AVATAR_TEST_S3_ACCESS_KEY` | Synthetic test key. |
| `AVATAR_TEST_S3_SECRET_KEY` | Synthetic test secret. |
| `AVATAR_TEST_S3_BUCKET` | Precreated test bucket. |

The complete native test setup is executable in `.github/workflows/ci.yml`.
Playwright uses mocked API responses and needs a production frontend build plus
Chromium. It does not need real backend credentials.
