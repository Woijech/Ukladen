# Ukladen

## Project Overview

Ukladen is a personal student productivity platform that combines:

- BSUIR university schedule;
- a flexible personal calendar;
- tasks and deadlines;
- reminders;
- notes;
- study materials;
- relations between workspace entities;
- search;
- an AI assistant;
- RAG over user materials.

The product concept combines ideas from **Google Calendar**, **Notion**, and task management systems while being specialized for the workflow of a BSUIR student.

Status: the product flows below are planned and not implemented.

## Core Idea

After registration, the user selects a university group and optionally a subgroup.

The system retrieves schedule data through the BSUIR IIS integration and creates a personal calendar view.

The imported university schedule is not treated as an immutable personal plan.

For example, a student can:

- mark a lecture as skipped;
- free that interval in the personal calendar;
- place a personal event in that time slot;
- attach notes;
- link tasks;
- attach study materials;
- create reminders.

Official schedule data and personal calendar state are logically separated.

## Architecture

Primary architecture document:

```text
SYSTEM_ARCHITECTURE.md
```

Architecture style:

```text
Modular Monolith
```

Main runtime components:

```text
Next.js Frontend
       |
       v
FastAPI Backend
       |
 +-----+---------+----------+
 |               |          |
 v               v          v
PostgreSQL      Redis     SeaweedFS/S3
+ pgvector        |
                  v
             Celery Workers
```

## Technology Stack

### Backend

```text
Python
FastAPI
Pydantic
SQLAlchemy
Alembic
httpx
```

### Data

```text
PostgreSQL
pgvector
PostgreSQL Full Text Search
Redis
```

### Async Processing

```text
Celery
Celery Beat
```

### Files

```text
SeaweedFS
S3-compatible object storage
```

### Frontend

```text
Next.js
React
TypeScript
TanStack Query
Zustand
FullCalendar
```

### DevOps

```text
Docker
Docker Compose
Traefik
GitHub Actions
```

### Quality

```text
uv
Ruff
Pyright
pytest
Playwright
```

## Backend Modules

```text
auth
users
academics
subjects
schedule
calendar
tasks
reminders
notes
materials
relations
search
ai
notifications
integrations
```

## Development Rules

Mandatory rules for AI coding agents and human developers are defined in:

```text
AGENTS.md
```

## Documentation Language

All technical documentation and code comments are written in English.

User-facing product text may initially be Russian.

## Current Status

Phase 0 foundation is implemented. The repository contains a FastAPI modular
monolith, Next.js shell, PostgreSQL 18/pgvector, Redis, Celery worker and Beat,
SeaweedFS object storage, Traefik, Docker Compose and GitHub Actions CI.
No business functionality is implemented.

```text
apps/backend     Python 3.14 API, module boundaries, migrations, workers, tests
apps/web         Next.js/React/TypeScript shell and browser tests
infra            Traefik routing
docs            Architecture, product and local development documents
```

Start from the repository root:

```bash
cp .env.example .env
docker compose up --build --detach --wait --wait-timeout 180
```

Open <http://localhost:8080> and <http://localhost:8080/api/docs>.
All published ports bind to localhost. The first image build requires network
access to download dependencies and images. These are local development settings.

Read [Local Development](docs/development/local-development.md) for host setup,
checks and troubleshooting. Implementation details are in
[Architecture Overview](docs/architecture/overview.md),
[Backend](docs/architecture/backend.md), [Frontend](docs/architecture/frontend.md)
and [Infrastructure](docs/architecture/infrastructure.md).

Local storage uses SeaweedFS; [ADR 0001](docs/adr/0001-use-seaweedfs.md) records
the provider decision. Production storage remains a separate deployment decision. Real IIS integration, authentication, calendar,
tasks, notes, materials, search, AI and RAG remain **not implemented**.
