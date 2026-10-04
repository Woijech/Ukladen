# Ukladen Infrastructure Foundation

Status: local Compose and home-server Cloudflare Tunnel configuration implemented.
Public activation requires account/DNS setup; managed production deployment is not implemented.

## Runtime

The Compose project is `ukladen`. Images are `ukladen-backend:local` and
`ukladen-web:local`; default data volumes are `ukladen_postgres-data` and
`ukladen_seaweedfs-data`. The default PostgreSQL database is `ukladen`.

| Process | Implementation |
| --- | --- |
| `api` | FastAPI/Uvicorn, backend image, non-root user. |
| `worker` | Celery worker, same backend image, concurrency 2. |
| `beat` | Celery Beat, same backend image, empty periodic schedule. |
| `web` | Next.js standalone server, non-root user. |
| `postgres` | PostgreSQL 18 image with pgvector available. |
| `redis` | Redis 7.4, temporary broker data, no persistent volume. |
| `seaweedfs` | SeaweedFS 4.48, single-process `weed mini`, non-root user. |
| `traefik` | Traefik 3.6, file-based HTTP routing without a Docker socket mount. |

One-shot `migrate` applies Alembic. SeaweedFS creates the configured bucket during
startup; there is no separate storage initializer. Startup waits for database,
Redis and storage health, successful migration, then API and frontend health.
Worker health uses Celery inspect ping. Beat has process monitoring only and writes
its empty schedule under `/tmp`. Run only one Beat instance.

PostgreSQL and SeaweedFS use separate named volumes. PostgreSQL 18's volume mounts
at `/var/lib/postgresql`; SeaweedFS's data mounts at `/data`.
`docker compose down` preserves volumes. Redis is deliberately ephemeral: pending
broker messages can be lost if its container is recreated. Durable queue recovery
and idempotent business jobs require design in their own slice.

## Object Storage

The upstream `chrislusf/seaweedfs:4.48` image runs master, volume, filer, S3 gateway
and Admin UI together in one process. Unused WebDAV, Iceberg and Lance endpoints are
disabled. No host Go compiler, custom storage image or additional application
dependency is needed.

`S3_ACCESS_KEY` and `S3_SECRET_KEY` seed the S3 credentials and configure password
authentication on the local Admin UI. `S3_BUCKET` seeds the initial bucket.
Anonymous object operations are not enabled. The S3 gateway provides `/readyz`
for container and API readiness probes; probes do not verify bucket permissions.
Application file upload/download functionality is not implemented.

The provider decision is recorded in [ADR 0001](../adr/0001-use-seaweedfs.md).
Old MinIO volumes are retained and cannot be attached directly to SeaweedFS.
Existing objects require a separate transfer through S3 clients.

## Local Exposure

All published ports bind to `127.0.0.1`: Traefik 8080, web 3000, API 8000,
PostgreSQL 5432, Redis 6379, SeaweedFS S3 8333 and Admin UI 23646. Other SeaweedFS
component ports are not published to the host. Traefik serves plain HTTP locally.
`.env.example` contains development credentials; `.env` is ignored by Git.
Managed production deployment, production service accounts, secrets management,
backup automation and redundancy are not implemented. A production storage provider
remains a separate deployment decision.

## Home Server Exposure

`docker-compose.home.yml` overlays the local stack, replaces backend env files
with `.env.home`, and removes all host port publications. Cloudflared 2026.9.3
connects outbound to Cloudflare and routes `ukladen.app` to Traefik on the dedicated
edge network. Cloudflare terminates browser TLS. Traefik trusts forwarded headers
only from cloudflared; Uvicorn trusts the Traefik and connector hops in the chain,
using fixed edge addresses outside the dynamic allocation range.
The home profile uses Secure cookies and the public HTTPS origin. Traefik access
logs are disabled to avoid recording authentication query data. Existing volumes
and restart policies are reused; backup automation and durable email delivery
remain unimplemented. See [ADR 0003](../adr/0003-use-cloudflare-tunnel-for-home-hosting.md)
and [setup instructions](../deployment/home-server.md).

## CI

GitHub Actions runs backend lint/format/type/tests, frontend lint/type/build/browser
tests, and a Compose build/start/health smoke check. uv and npm lockfiles are used
for reproducible application installs. Infrastructure/base image tags are explicit
but not digest-pinned. CI is a verification baseline; it does not publish or deploy.
