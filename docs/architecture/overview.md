# Architecture Overview

Status: foundation implemented; business functionality is not implemented.

`SYSTEM_ARCHITECTURE.md` remains the primary architecture contract. The repository
contains one Python backend and one Next.js frontend. The API, Celery worker and
Celery Beat use the same backend image and codebase. They are processes of a modular
monolith, not independent services with separate business data.

PostgreSQL 18 is the authoritative data store. The initial Alembic migration enables
pgvector; there are no business tables. Redis is the Celery broker. SeaweedFS is local
S3-compatible storage; startup creates a private `materials` bucket by default.
Traefik routes `/api` to FastAPI and other paths to Next.js on one local origin.

The implemented HTTP surface is operational: API liveness/readiness, OpenAPI and
frontend liveness. The frontend renders a shell and an API connection indicator.

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

Status: not implemented — authentication, academic onboarding, IIS integration,
calendar resolution, tasks, reminders, notes, materials, relations, search,
notifications, AI and RAG. Observability beyond process/access logs, production
TLS, production credentials and deployment automation are not implemented.

The storage provider replacement is recorded in [ADR 0001](../adr/0001-use-seaweedfs.md).
Production storage remains a separate deployment decision. The modular monolith
architecture is unchanged.
