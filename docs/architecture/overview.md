# Ukladen Architecture Overview

Status: foundation, backend authentication, user profiles, academic profiles and
public university/schedule reads implemented.

The product name is **Ukladen**. Technical identifiers use lowercase `ukladen`:
the Compose project, Celery application and default PostgreSQL database. Package
and image names are `ukladen-backend` and `ukladen-web`.

`SYSTEM_ARCHITECTURE.md` remains the primary architecture contract. The repository
contains one Python backend and one Next.js frontend. The API, Celery worker and
Celery Beat use the same backend image and codebase. They are processes of a modular
monolith, not independent services with separate business data.

PostgreSQL 18 is the authoritative data store. The initial Alembic migration enables
pgvector; subsequent migrations create users, auth and academic-profile tables.
Redis serves Celery, session caching, OAuth state and request protection. SeaweedFS is local
S3-compatible storage; startup creates a private `materials` bucket by default.
Traefik routes `/api` to FastAPI and other paths to Next.js on one local origin.

The HTTP surface includes health checks, browser authentication, user and academic
profiles, university directories and schedule queries. See the
[backend architecture](backend.md) and [university read API](../development/university-api.md).

## Boundaries

Fourteen business packages exist under `app/modules`: auth, users, academics,
subjects, schedule, calendar, tasks, reminders, notes, materials, relations,
search, ai and notifications. The fifteenth boundary, integrations, lives at
`app/integrations`, following the architecture document's repository tree.
Its adapter packages are bsuir, llm, embeddings and storage.

Unused boundaries contain only package markers. No speculative entities, DTOs or
repositories are generated. When a vertical slice is implemented, its dependencies
must follow `presentation -> application -> domain`, with infrastructure implementing
application-owned ports. Domain code must remain independent of frameworks and
external clients. Inter-module access must use application services or interfaces.

## Scope

Status: not implemented — calendar resolution, schedule persistence/synchronization,
tasks, reminders, notes, materials, relations, search,
notifications, AI and RAG. Observability beyond process/access logs, production
TLS, production credentials and deployment automation are not implemented.

The storage provider replacement is recorded in [ADR 0001](../adr/0001-use-seaweedfs.md).
Production storage remains a separate deployment decision. The modular monolith
architecture is unchanged.
