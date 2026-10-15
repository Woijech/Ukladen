# Application logging

Status: structured API/Celery diagnostics and browser failure logging implemented. No remote log collector,
metrics service or browser telemetry upload is configured.

The backend writes one JSON object per line to stderr. `LOG_LEVEL` controls the
`app` loggers (`INFO` by default; also `DEBUG`, `WARNING`, `ERROR`, `CRITICAL`).
It does not enable third-party HTTP, SQL or SDK debug dumps. Dependencies retain
warning/error diagnostics with their logger name, exception type and safe stack
locations; their free-form messages are omitted because they may contain secrets.

Every HTTP response includes a server-generated `X-Request-ID`. Request summaries
record the method, matched route template, status and duration. Queries, bodies,
headers, cookies, raw path parameters and unmatched URLs are omitted. Successful
health probes are `DEBUG`; rejected requests are `WARNING`; server failures are
`ERROR`. Application failures keep exception types and stack locations, without
exception messages, source text, chained exception payloads or local variables.

The producer propagates the request ID in Celery protocol-2 headers and logs
accepted publication with `published_task_id` / `published_task_name`. Task logs
include the task ID, known task name, state and duration, without arguments or
return values. Periodic jobs have a task ID but no originating HTTP request ID.
Request/task contexts are reset after execution.

Standalone Alembic commands use the same safe logger for migration start,
completion and failure. Embedded migrations preserve the host application's
logging configuration.

## Operational events

API handlers record handled service failures before returning safe responses.
Dependency adapters record IIS transport/response validation, Google token/key
failures, Redis session/cache/state/limiter failures (including cache fallback),
SMTP delivery and S3 failures. S3 error codes are allowlisted; SDK error payloads
are omitted. Avatar cleanup/recovery failures are visible without object keys.
Authentication redirects log rejection categories without OAuth query data.

Calendar reads record resolved event counts and schedule source state. Personal-event
creation/update/deletion and override writes/deletion are logged only after commit.
Calendar rejections record fixed reasons with safe exception locations. Existing request
IDs correlate these events; titles, descriptions, locations, event UUIDs and input times
are omitted. See [calendar contracts](calendar.md) for the event names.

Schedule imports record start, final source state, group ID/number, event count
and duration. Unsupported recurrence reasons are allowlisted (for example
`split_precedence`). An obsolete import is explicitly logged as discarded and
reports zero applied events. Due-group dispatch records selected/queued counts.
Expected import failures are stored as source state, so `task.finished` can have
`SUCCESS` while `schedule.sync_finished` has `error` or `unsupported`. Inspect
the latter or the authenticated `GET /api/v1/schedule/me/sync-status` endpoint.

Reminder dispatch uses the known task name `reminders.dispatch_due` and normal task
start/finish/retry diagnostics. Fixed `reminders.delivery_failed` and
`reminders.dispatch_failed` events record safe failure locations without exception
messages, reminder payloads or event titles. Retried batches may already contain
successfully committed deliveries; inbox deduplication prevents repeats.

Material jobs use the known task names `materials.dispatch` and `materials.process`.
Fixed `materials.cleanup_failed`, `materials.dispatch_failed` and `materials.task_failed`
events record sanitized failure locations without document text, filenames, URLs,
storage keys or raw parser messages. Processing outcomes remain in material metadata;
a successful task can record a terminal parser failure rather than indexing text.

The browser console records fixed JSON events for failed health checks, email
verification network/API failures, and rendering boundaries. Failed API responses
include a validated request ID when available. Browser messages, stacks, token
fragments and response bodies are omitted. Browser diagnostics stay in DevTools;
they are not uploaded. Next.js retains its native server diagnostics.

Docker uses the `json-file` driver with three files of up to 10 MB per container,
including the home tunnel. Rotation takes effect after container recreation.
Traefik raw access logs are disabled in both profiles to avoid OAuth query leakage;
API request summaries provide safe access diagnostics. Proxy/tunnel process logs
remain available through Compose.

```bash
docker compose logs -f --tail=100 --timestamps api worker material-worker beat
docker compose logs --since=30m api worker material-worker | rg '"level": "(ERROR|WARNING)"'
docker compose logs --since=30m api worker material-worker | rg '<request-id-from-response>'
```

For the home deployment, use the same `--env-file .env.home -f docker-compose.yml
-f docker-compose.home.yml` options as when starting the stack. `Ctrl+C` stops
following logs without stopping services. Source/configuration changes require
rebuilding the backend image and recreating API/worker/Beat containers.
Frontend changes require rebuilding/recreating `web` as well. Changing `LOG_LEVEL`
requires container recreation; changing application code requires a rebuild.

For an existing running local stack:

```bash
docker compose build api web
docker compose run --rm --no-deps migrate
docker compose up -d --no-deps api worker material-worker beat web traefik
```

For the home stack, add `--env-file .env.home -f docker-compose.yml
-f docker-compose.home.yml` immediately after `docker compose` in each command.
These commands leave the database, Redis and storage containers running. Their
rotation settings, and the tunnel's, take effect on their next recreation.

New log calls must use fixed event names and explicit safe scalar metadata. Never
log passwords, session/CSRF/OAuth tokens, token hashes, email recipients, connection
URLs, SQL parameters, uploaded content or upstream response bodies. Use
`core.logging.log_failure` rather than interpolating exception strings.
