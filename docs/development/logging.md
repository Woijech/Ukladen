# Application logging

Status: structured API and Celery logging implemented. No remote log collector,
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

The producer propagates the request ID in Celery protocol-2 headers. Task logs
include the task ID, known task name, state and duration, without arguments or
return values. Periodic jobs have a task ID but no originating HTTP request ID.
Request/task contexts are reset after execution.

```bash
docker compose logs -f --tail=100 --timestamps api worker beat
docker compose logs --since=30m api worker | rg '"level": "(ERROR|WARNING)"'
docker compose logs --since=30m api worker | rg '<request-id-from-response>'
```

For the home deployment, use the same `--env-file .env.home -f docker-compose.yml
-f docker-compose.home.yml` options as when starting the stack. `Ctrl+C` stops
following logs without stopping services. Source/configuration changes require
rebuilding the backend image and recreating API/worker/Beat containers.

New log calls must use fixed event names and explicit safe scalar metadata. Never
log passwords, session/CSRF/OAuth tokens, token hashes, email recipients, connection
URLs, SQL parameters, uploaded content or upstream response bodies. Use
`core.logging.log_failure` rather than interpolating exception strings.
