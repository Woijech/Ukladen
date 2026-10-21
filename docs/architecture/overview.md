# Ukladen Architecture Overview

Status: foundation, backend authentication, user profiles, academic profiles and
public university reads, persisted official schedule synchronization and the backend
personal calendar, pages/block documents, relations, collection/tag organization
and saved calendar views, calendar reminders, durable in-app notifications, private
materials and basic full-text search implemented.

The product name is **Ukladen**. Technical identifiers use lowercase `ukladen`:
the Compose project, Celery application and default PostgreSQL database. Package
and image names are `ukladen-backend` and `ukladen-web`.

`SYSTEM_ARCHITECTURE.md` remains the primary architecture contract. The repository
contains one Python backend and one Next.js frontend. The API, Celery workers and
Celery Beat use the same backend image and codebase. They are processes of a modular
monolith, not independent services with separate business data.

The target combines independent pages and a user-organized calendar with AI and deep
IIS integration. Subjects are optional; source labels do not merge lecture/lab occurrences.
[ADR 0004](../adr/0004-keep-workspace-organization-optional.md) and
[workspace architecture](workspace.md) describe implemented slices and the remaining target.
See [requirements](../product/workspace.md), [decisions](../product/open-questions.md)
and [roadmap](../development/implementation-roadmap.md).

Confirmed current target: personal pages/blocks/databases with table/calendar views.
Formulas, sharing and student-account IIS are deferred. AI includes recommendations,
confirmed execution and scoped automatic actions under
[ADR 0005](../adr/0005-support-scoped-ai-action-permissions.md); runtime remains unimplemented.

PostgreSQL 18 is the authoritative data store. The initial Alembic migration enables
pgvector; subsequent migrations create users, auth, academic-profile, personal-event
and official schedule tables.
Redis serves Celery, session caching, OAuth state and request protection. SeaweedFS is local
S3-compatible storage; startup creates a private `materials` bucket by default.
Traefik routes `/api` to FastAPI and other paths to Next.js on one local origin.

The HTTP surface includes health checks, browser authentication, user and academic
profiles, university directories, live schedule queries, stored dated events and the
resolved personal calendar. See [calendar contracts](../development/calendar.md) and the
[backend architecture](backend.md) and [university read API](../development/university-api.md).

The calendar module implements personal events, resolution and official overrides.
The weekly UI supports personal-event create/edit/delete. Conflicts and free slots
are not implemented; see
[calendar contracts](../development/calendar.md).

## Boundaries

Fifteen business packages exist under `app/modules`: auth, users, academics,
subjects, schedule, calendar, tasks, reminders, notes, materials, relations,
search, ai, notifications and workspace. The integrations boundary lives at
`app/integrations`, following the architecture document's repository tree.
Its adapter packages are bsuir, llm, embeddings and storage.

The `workspace` boundary implements collections, tags, typed membership and saved
calendar views and database/property/record APIs with saved table/calendar views,
nonblocking date projection, versioned moves and mixed calendar display.

Unused boundaries contain only package markers. No speculative entities, DTOs or
repositories are generated. When a vertical slice is implemented, its dependencies
must follow `presentation -> application -> domain`, with infrastructure implementing
application-owned ports. Domain code must remain independent of frameworks and
external clients. Inter-module access must use application services or interfaces.

## Scope

Status: not implemented — free slots, conflict checks, task blocks,
tasks, task/deadline reminders, semantic search, AI and RAG.
Private materials, bounded document extraction, optional page attachments and lexical
search are implemented, backend only; see [materials/search](../development/materials.md).
One-shot calendar reminders and the durable inbox are implemented,
backend only; see [reminder contracts](../development/reminders.md).
Structured diagnostics, request/task correlation and
container log rotation are implemented; see [logging](../development/logging.md).
The home-hosting overlay supports browser TLS through Cloudflare Tunnel; public
activation requires operator account/DNS setup. Remote observability services,
metrics, tracing, managed production credentials and deployment automation are
not implemented. See [infrastructure profiles](infrastructure.md).

Standalone nested pages, flat typed blocks, page/calendar links and collections/tags
are implemented; see [notes](../development/notes.md), [relations](../development/relations.md)
and [workspace](../development/workspace.md), plus [saved calendar views](../development/calendar-views.md).
Database/property/record APIs, table/calendar views and mixed date projection are
also implemented, backend only. Rich/nested blocks are not implemented. Authenticated IIS capabilities remain
unverified/unimplemented; see the [IIS roadmap](../integrations/bsuir-iis-roadmap.md).

The storage provider replacement is recorded in [ADR 0001](../adr/0001-use-seaweedfs.md).
Production storage remains a separate deployment decision. The modular monolith
architecture is unchanged.
