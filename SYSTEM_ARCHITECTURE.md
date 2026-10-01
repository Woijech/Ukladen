# SYSTEM_ARCHITECTURE.md

> **Project:** Ukladen  
> **Document type:** High-Level Architecture Blueprint  
> **Goal:** Define the overall architecture, boundaries, runtime components, technology stack, module ownership and scaling path.  
> **Important:** This document intentionally does **not** define concrete BSUIR IIS response fields, exact external API payloads, full SQL schema, or detailed endpoint DTOs. Those contracts are separate documents.

---

# 1. Product Vision

The system is a flexible student workspace inspired by **Notion + Google Calendar + task manager**, specialized for BSUIR students.

The central object for the user is a **personal calendar/workspace**.

The system combines:

- university schedule imported from BSUIR IIS;
- flexible personal calendar;
- tasks and deadlines;
- reminders;
- subjects;
- notes;
- educational materials;
- links between entities;
- AI assistant;
- semantic search and RAG.

The user must be able to freely adapt the imported university schedule for personal planning:

- mark a class as skipped;
- hide it from the personal view;
- replace the occupied time with a personal activity;
- attach notes/tasks/materials;
- customize the local representation.

Official schedule data and the user's personal interpretation are logically separated.

---

# 2. Architecture Style

Use a:

```text
MODULAR MONOLITH
+
BACKGROUND WORKERS
+
SHARED DATA PLATFORM
```

Do **not** start with microservices.

Core principles:

```text
1. One main backend application.
2. Strong module boundaries.
3. One PostgreSQL database for core business data.
4. Redis for cache, queue broker, locks and rate limiting.
5. Celery workers for asynchronous/background tasks.
6. S3-compatible storage for files.
7. AI isolated behind interfaces and tools.
8. External integrations isolated behind adapters.
9. Backend is stateless.
10. Modules communicate through application services/interfaces, not random imports.
```

---

# 3. High-Level System Diagram

```text
                               Internet
                                  |
                                  v
                         +------------------+
                         | Reverse Proxy    |
                         | Traefik / Nginx  |
                         +--------+---------+
                                  |
                   +--------------+--------------+
                   |                             |
                   v                             v
          +------------------+          +------------------+
          | Frontend         |          | Backend API      |
          | Next.js / React  |<-------->| FastAPI          |
          +------------------+   REST   +--------+---------+
                                                   |
                       +---------------------------+---------------------------+
                       |                           |                           |
                       v                           v                           v
              +------------------+        +------------------+        +------------------+
              | PostgreSQL       |        | Redis            |        | S3 storage       |
              | + pgvector       |        | cache / broker   |        | files            |
              +------------------+        +--------+---------+        +------------------+
                                                  |
                                      +-----------+-----------+
                                      |                       |
                                      v                       v
                               +-------------+          +-------------+
                               | Celery      |          | Celery Beat |
                               | Workers     |          | Scheduler   |
                               +------+------+          +-------------+
                                      |
                 +--------------------+-----------------------+
                 |                    |                       |
                 v                    v                       v
          +-------------+       +-------------+         +-------------+
          | IIS Adapter |       | AI / RAG    |         | Notifications|
          +-------------+       +-------------+         +-------------+
```

---

# 4. Runtime Components

## 4.1 Frontend

Responsibilities:

```text
- authentication UI;
- onboarding;
- group/subgroup selection;
- calendar day/week/month views;
- drag & drop;
- event resizing;
- personal event creation/editing;
- imported schedule event overrides;
- tasks and deadlines UI;
- subject workspace;
- notes;
- materials;
- AI assistant UI;
- filters and search.
```

Recommended stack:

```text
Next.js
React
TypeScript
TanStack Query
Zustand
FullCalendar
```

Frontend must not implement business-critical rules such as:

```text
- free-slot calculation;
- event conflict truth;
- schedule synchronization logic;
- permissions;
- AI business actions.
```

These belong to the backend.

---

## 4.2 Core Backend API

Technology:

```text
Python
FastAPI
Pydantic
SQLAlchemy
Alembic
```

Responsibilities:

```text
- authentication;
- users;
- academic profile;
- subjects;
- schedule;
- personal calendar;
- schedule overrides;
- tasks;
- deadlines;
- reminders;
- notes;
- materials metadata;
- relations;
- search;
- AI tool layer;
- orchestration;
- authorization;
- business rules.
```

The backend is a **modular monolith**.

---

## 4.3 PostgreSQL

Use PostgreSQL as the main source of truth.

Store:

```text
users
academic profiles
groups
subjects
official schedule
personal schedule overrides
personal calendar events
tasks
task relations
reminders
notes
materials metadata
knowledge relations
AI sessions
processing state
```

Use:

```text
PostgreSQL relational model
JSONB for extensible metadata
PostgreSQL Full Text Search
pgvector for embeddings
```

---

## 4.4 Redis

Redis responsibilities:

```text
Celery broker
cache
distributed locks
rate limiting
idempotency keys
temporary state
short-lived AI cache
```

Redis must never become the canonical store for user data.

---

## 4.5 Celery

Celery is part of the architecture from the beginning.

Use workers for:

```text
schedule synchronization
document processing
text extraction
embedding generation
RAG indexing
notifications
reminders
cleanup jobs
heavy AI tasks
future imports/exports
```

Use Celery Beat for periodic work:

```text
periodic IIS synchronization
reminder checks
maintenance
re-index jobs
```

Initial broker:

```text
Redis
```

Possible future migration:

```text
RabbitMQ
```

---

## 4.6 Object Storage

Local provider decision: [ADR 0001](docs/adr/0001-use-seaweedfs.md).

Use:

```text
SeaweedFS in local/dev
S3-compatible storage in production
```

Store:

```text
PDF
DOCX
images
attachments
educational files
```

PostgreSQL stores only:

```text
metadata
object key
ownership
processing state
relations
```

---

## 4.7 AI / RAG

AI is a separate logical module, initially inside the modular monolith.

Responsibilities:

```text
natural-language request interpretation
intent classification
tool calling
knowledge retrieval
RAG
semantic search
answer generation
action proposals
```

AI must not access the DB directly.

Architecture:

```text
             LLM
              |
              v
        +-------------+
        | Tool Layer  |
        +------+------+ 
               |
     +---------+---------+
     |         |         |
     v         v         v
 Calendar    Tasks    Knowledge
 Service     Service    Service
     \         |         /
      +--------+--------+
               |
               v
          PostgreSQL
```

---

# 5. Main Backend Modules

```text
auth
users
academics
schedule
calendar
tasks
reminders
subjects
notes
materials
relations
search
ai
notifications
integrations
```

## 5.1 auth

```text
registration
login
opaque server-side browser sessions
logout
password hashing
sessions
```

Browser authentication uses HttpOnly cookies, PostgreSQL as the canonical session
store and Redis as a session cache. Only session token hashes are persisted.
[ADR 0002](docs/adr/0002-use-opaque-browser-sessions.md) records this decision.
Status: runtime authentication is not implemented.

## 5.2 users

```text
profile
timezone
locale
preferences
account state
```

## 5.3 academics

```text
group
subgroup
semester
subjects
academic profile
```

## 5.4 schedule

```text
official university schedule
schedule synchronization
normalization of external schedule data
source state
```

Important:

```text
official schedule != personal calendar
```

## 5.5 calendar

```text
personal calendar
resolved calendar
personal events
schedule overrides
free slots
conflicts
occupied intervals
```

Conceptually:

```text
official schedule
        |
        v
user override layer
        |
        + personal events
        |
        v
resolved personal calendar
```

## 5.6 tasks

```text
tasks
deadlines
priority
status
estimated duration
dependencies
study blocks
task scheduling
```

## 5.7 reminders

```text
task reminders
calendar reminders
deadline reminders
notification scheduling
```

## 5.8 subjects

A subject is a workspace context:

```text
ПБЗ
|
|-- schedule
|-- tasks
|-- notes
|-- materials
|-- deadlines
`-- related events
```

## 5.9 notes

```text
student notes
markdown/text content
search
links to subjects/tasks/events/materials
```

## 5.10 materials

```text
file metadata
upload workflow
external links
processing state
text extraction
document indexing
```

## 5.11 relations

Notion-like links:

```text
task -> material
task -> note
subject -> material
calendar event -> note
schedule event -> task
note -> note
```

## 5.12 search

```text
structured search
PostgreSQL Full Text Search
semantic search
pgvector
RAG retrieval
```

## 5.13 ai

```text
LLM provider abstraction
tool registry
RAG orchestration
context building
AI sessions
action confirmation
```

## 5.14 notifications

```text
in-app notifications
future email
future Telegram
future push notifications
```

## 5.15 integrations

Initial:

```text
BSUIR IIS
LLM provider
embedding provider
S3-compatible storage
```

Future:

```text
Google Calendar
Microsoft Calendar
Telegram
email
other university systems
```

---

# 6. Backend Internal Architecture

Each major module follows:

```text
domain
application
infrastructure
presentation
```

Example:

```text
calendar/
|
|-- domain/
|   |-- entities
|   |-- value objects
|   |-- rules
|   `-- domain errors
|
|-- application/
|   |-- services
|   |-- commands
|   |-- queries
|   |-- DTO
|   `-- ports/interfaces
|
|-- infrastructure/
|   |-- SQLAlchemy repository
|   |-- Redis cache
|   `-- external implementations
|
`-- presentation/
    |-- FastAPI routes
    `-- request/response schemas
```

Allowed dependencies:

```text
presentation -> application -> domain

infrastructure -> application interfaces
infrastructure -> domain
```

Forbidden:

```text
domain -> FastAPI
domain -> SQLAlchemy
domain -> Redis
domain -> Celery
domain -> LLM SDK
```

---

# 7. Repository Structure

```text
ukladen/
|
|-- apps/
|   |
|   |-- backend/
|   |   |-- src/app/
|   |   |   |
|   |   |   |-- core/
|   |   |   |-- db/
|   |   |   |-- modules/
|   |   |   |   |-- auth/
|   |   |   |   |-- users/
|   |   |   |   |-- academics/
|   |   |   |   |-- schedule/
|   |   |   |   |-- calendar/
|   |   |   |   |-- tasks/
|   |   |   |   |-- reminders/
|   |   |   |   |-- subjects/
|   |   |   |   |-- notes/
|   |   |   |   |-- materials/
|   |   |   |   |-- relations/
|   |   |   |   |-- search/
|   |   |   |   |-- ai/
|   |   |   |   `-- notifications/
|   |   |   |
|   |   |   |-- integrations/
|   |   |   |   |-- bsuir/
|   |   |   |   |-- llm/
|   |   |   |   |-- embeddings/
|   |   |   |   `-- storage/
|   |   |   |
|   |   |   `-- workers/
|   |   |
|   |   |-- tests/
|   |   |-- alembic/
|   |   |-- pyproject.toml
|   |   `-- Dockerfile
|   |
|   `-- web/
|       |-- src/
|       |   |-- app/
|       |   |-- entities/
|       |   |-- features/
|       |   |-- widgets/
|       |   `-- shared/
|       |
|       |-- package.json
|       `-- Dockerfile
|
|-- infra/
|   |-- traefik/
|   `-- postgres/
|
|-- docs/
|   |-- architecture/
|   |-- adr/
|   `-- product/
|
|-- docker-compose.yml
|-- .env.example
|-- README.md
|-- AGENTS.md
`-- SYSTEM_ARCHITECTURE.md
```

---

# 8. Main Data Domains

Exact DB schema is a separate specification.

At architecture level:

```text
User
AcademicProfile
UniversityGroup
Subject
Teacher
Room

OfficialScheduleEvent
ScheduleOverride
PersonalCalendarEvent

Task
TaskDependency
TaskCalendarBlock

Reminder

Note
Material
MaterialChunk

EntityRelation

AISession
AIMessage
```

---

# 9. Main Data Flows

## 9.1 Onboarding

```text
User
 |
 v
Select group/subgroup
 |
 v
Backend
 |
 v
Schedule integration
 |
 v
Normalize data
 |
 v
PostgreSQL
 |
 v
Resolved Calendar API
 |
 v
Frontend Calendar
```

## 9.2 Personal schedule override

```text
Official lesson
      |
      v
User: "skip"
      |
      v
Schedule Override
      |
      v
Resolved Calendar
      |
      +-- official lesson remains known
      |
      `-- personal time becomes available
```

## 9.3 Task planning

```text
Task
 |
 +--> deadline
 +--> estimated duration
 +--> subject
 |
 v
Calendar Service
 |
 v
Free Slot Service
 |
 v
Task Calendar Block
```

## 9.4 File / RAG flow

```text
Upload material
      |
      v
SeaweedFS / S3
      |
      v
Material metadata
      |
      v
Celery
      |
      +--> text extraction
      +--> chunking
      +--> embeddings
      |
      v
PostgreSQL + pgvector
```

## 9.5 AI flow

```text
User request
    |
    v
AI module
    |
    +--> determine intent
    |
    +--> call application tools
    |       |
    |       +--> calendar
    |       +--> tasks
    |       +--> notes
    |       +--> materials
    |       `--> search
    |
    +--> RAG if needed
    |
    v
LLM
    |
    v
Response / Proposed Action
```

---

# 10. Preferred Technology Stack

## Backend

```text
Python 3.14.x
FastAPI
Pydantic v2
SQLAlchemy 2.x
Alembic
httpx
```

## Database

```text
PostgreSQL 18.x
pgvector
PostgreSQL Full Text Search
```

## Async / infrastructure

```text
Redis
Celery
Celery Beat
```

## Files

```text
SeaweedFS
S3-compatible API
```

## AI

```text
LLM provider abstraction
Tool Calling
Embeddings
RAG
pgvector
```

## Frontend

```text
Next.js
React
TypeScript
TanStack Query
Zustand
FullCalendar
```

## DevOps

```text
Docker
Docker Compose
Traefik
GitHub Actions
```

## Quality

```text
uv
Ruff
Pyright
pytest
Playwright
```

## Observability

```text
structured logging
Sentry
Prometheus
Grafana
OpenTelemetry
```

---

# 11. Local Development Deployment

```text
docker compose
|
+-- web
+-- api
+-- worker
+-- beat
+-- postgres
+-- redis
+-- seaweedfs
`-- traefik
```

The backend application code is shared by:

```text
api
worker
beat
```

but they run as separate processes.

---

# 12. Production Evolution

## Stage 1

```text
web x1
api x1
worker x1
beat x1
postgres
redis
object storage
```

## Stage 2

```text
web xN
api xN
worker xN

managed PostgreSQL
managed Redis
S3
load balancer
```

Backend remains stateless.

## Stage 3

Extract services only when justified:

```text
Core API
AI Service
Document Processing Service
Notification Service
```

---

# 13. Team Distribution

Team:

```text
1 Frontend developer
2 Backend developers
```

This means two backend developers, **not two separate backend systems**.

## Frontend developer

Primary ownership:

```text
apps/web
calendar UI
tasks UI
subject workspace
notes/materials UI
AI assistant UI
```

## Backend developer A — Core/Planning

```text
auth
users
academics
subjects
schedule
calendar
tasks
reminders
```

## Backend developer B — Knowledge/AI

```text
notes
materials
relations
search
ai
notifications
workers
```

Shared:

```text
database migrations
common infrastructure
API conventions
Docker
CI/CD
architecture decisions
```

---

# 14. Development Order

## Phase 0

```text
repository
Docker Compose
FastAPI
Next.js
PostgreSQL
Redis
Celery
SeaweedFS
CI
```

## Phase 1

```text
auth
user
academic profile
schedule provider abstraction
schedule storage
calendar
personal events
schedule overrides
```

Goal:

```text
group
-> schedule
-> personal calendar
-> skip class
-> create own event
```

## Phase 2

```text
subjects
tasks
deadlines
free slots
task blocks
reminders
```

## Phase 3

```text
notes
materials
relations
object storage
document processing
```

## Phase 4

```text
search
embeddings
pgvector
RAG
```

## Phase 5

```text
AI assistant
tool calling
action confirmation
```

## Phase 6

```text
performance
monitoring
deployment
external integrations
```

---

# 15. Architecture Rules for AI Coders

```text
1. Do not create microservices in MVP.
2. Keep one backend codebase.
3. Preserve module boundaries.
4. Do not put business logic in FastAPI routes.
5. Do not put SQL in FastAPI routes.
6. Use Alembic for DB changes.
7. Do not let LLM access DB directly.
8. Keep external APIs behind adapters.
9. Keep file binaries outside PostgreSQL.
10. Use Redis only for temporary/cache/queue responsibilities.
11. Async/background jobs must be idempotent.
12. Backend must remain stateless.
13. Do not invent external API contracts.
14. Do not add infrastructure technology without an architectural reason.
15. Build vertical slices instead of generating the whole system at once.
```

---

# 16. Architecture Documents Split

This document defines only system architecture.

Separate documents should later define implementation details:

```text
SYSTEM_ARCHITECTURE.md   <- overall system
DATABASE_SPEC.md         <- exact schema
API_SPEC.md              <- exact REST contracts
IIS_INTEGRATION_SPEC.md  <- IIS integration
AI_RAG_SPEC.md           <- AI/RAG/tool contracts
FRONTEND_SPEC.md         <- UI/frontend architecture
DEPLOYMENT_SPEC.md       <- production infrastructure
```

This separation prevents the high-level architecture from becoming coupled to currently unknown integration details.

---

# 17. Final Architecture Summary

```text
                         Next.js Frontend
                                |
                                v
                           FastAPI API
                                |
          +---------------------+---------------------+
          |                     |                     |
          v                     v                     v
     PostgreSQL               Redis                SeaweedFS/S3
     + pgvector                 |
                                v
                           Celery Workers
                                |
                 +--------------+---------------+
                 |                              |
                 v                              v
             IIS Adapter                    AI / RAG
```

Architecture style:

```text
Modular Monolith
```

Data:

```text
PostgreSQL
```

Async:

```text
Redis + Celery
```

Files:

```text
S3-compatible object storage
```

AI:

```text
RAG + tool calling
```

Scaling path:

```text
horizontal replicas first
microservice extraction only when justified
```

This architecture is intentionally simple enough for MVP development while preserving a clear path to a scalable production system.
