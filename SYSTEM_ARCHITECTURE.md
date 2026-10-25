# SYSTEM_ARCHITECTURE.md

> **Project:** Ukladen
>
> **Document type:** Primary architecture contract (current baseline and target design)
>
> **Goal:** Define the overall architecture, boundaries, runtime components, technology stack, module ownership and scaling path.
>
> **Important:** This document intentionally does **not** define concrete BSUIR IIS response fields, exact external API payloads, full SQL schema, or detailed endpoint DTOs. Those contracts are separate documents.

Updated: 2026-10-24. Target features are not implemented unless explicitly marked.
Read the [documentation index](docs/README.md), [open decisions](docs/product/open-questions.md)
and [implementation roadmap](docs/development/implementation-roadmap.md) for a concrete slice.
[ADR 0004](docs/adr/0004-keep-workspace-organization-optional.md) records optional organization.

---

# 1. Product Vision

Ukladen combines a **Notion-like workspace + Notion Calendar-like calendar + AI
assistant + deep BSUIR IIS integration**. These references describe product intent,
not an obligation to reproduce every feature of another product.

The user has independent pages and a personal calendar. Academic and personal
content are equally valid. A group/subgroup selection enriches the calendar; it
is not required to create a page, personal event or task.

User-controlled organization is the architecture contract:

- pages/notes exist without subjects, events, parents or collections;
- events are edited directly and retain their individual identities;
- page nesting, links, tags, collections and views are optional choices;
- matching subject labels never merge lectures/labs or create shared content;
- views select/present data without owning, copying or deleting it;
- grouping never propagates member edits;
- dates/deadlines are not busy time unless explicitly scheduled;
- official facts remain separate from personal interpretation and organization.

The full target includes blocks, user-defined databases/properties, saved views,
tasks, reminders, materials, search/RAG and application-tool-based AI. The owner
confirmed pages, blocks and user databases, with mandatory table/calendar views.
Formulas and collaboration are deferred. Current IIS scope is schedule and related
public data; grades/private accounts remain future-only. Exact content/schema details
and scoped AI permission rules are in the decision register. Private IIS work requires
an explicit later phase and verified contracts; do not implement it in current slices.

Current backend: authentication, profiles, public IIS reads, official schedule
storage/sync, personal events, official overrides, resolved calendar reads, standalone
nested pages with versioned blocks and Markdown compatibility, branch trash and
optional page/calendar links, collections/tags with typed memberships and saved
calendar views and recoverable user databases/properties/page-backed records.
Saved table/calendar database views, date projection and date moves are implemented.
Additive mixed calendar display is implemented through application query ports.
One-shot calendar reminders and durable in-app notifications are implemented.
Private materials, bounded document extraction, page attachments and basic PostgreSQL
full-text search are implemented; see [materials/search](docs/development/materials.md).
Status: not implemented — tasks, availability, semantic search, RAG and authenticated IIS.
AI-03 read tools are implemented locally but unactivated; see the AI section below.
The frontend implements login/registration, browser email verification and password
recovery, optional academic-group selection, day/week personal-event CRUD, flat block
pages, materials, explicit organization, database table/calendar views, full-text
search, reminders/inbox and profile/avatar settings. Its shared light/dark shell
preserves the existing API, session and calendar contracts. Official override editing,
saved event views and mixed date projection remain API-only. Tasks require their future
backend. The AI-04 chat/settings/usage UI is implemented locally; AI remains default-disabled and unactivated. See the [frontend guide](docs/architecture/frontend.md).

Detailed behavior: [product overview](docs/product/overview.md) and
[workspace requirements](docs/product/workspace.md).

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
- standalone/nested pages and optional academic organization;
- block editing and user-defined database views (planned);
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
- user organization and saved calendar views;
- optional subjects;
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
optional subjects
pages, versioned documents, collections, tags, typed memberships and saved calendar views
database/property definitions and page-backed records with typed values
saved table/calendar view settings and nonblocking database date projections
official schedule
personal schedule overrides
personal calendar events
tasks
task relations
reminders
page content (notes)
materials metadata
optional knowledge relations
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
owner-scoped source citations and versioned confirmed/scoped automatic execution
```

AI must not access the DB directly. It uses the caller's normal permissions through
application tools. Read-only help/recommendations precede writes. Writes require
exact confirmation or an explicit matching owner-issued automatic-action grant,
version checks and durable idempotency. Retrieved content cannot grant authorization.
[ADR 0005](docs/adr/0005-support-scoped-ai-action-permissions.md) records these paths.
The owner-confirmed [AI specification](docs/product/ai.md) selects provider-neutral
operator offerings and personal API connections, local-source-first answers with
labeled model/web fallback, editable personal instructions and opt-in proactive work.
[ADR 0009](docs/adr/0009-specify-provider-neutral-ai-orchestration.md) records one
logical LangChain create_agent agent on LangGraph with PostgreSQL checkpoints behind
neutral ports. Reuse tool schemas and HITL middleware; normal services still own
authorization, replay protection and atomic commits. Calendar
services own interval truth; tasks owns deterministic planning. A stale confirmed
multi-action plan applies nothing and needs a new preview. Per-account activation
settings and actual per-owner grants remain required. See [AI architecture](docs/architecture/ai.md).
Status: AI-00 and the offline AI-01 foundation are complete. Owned persistence
adapters/migrations are natively tested on disposable PostgreSQL, unapplied to the app.
The default-disabled [offline API](docs/development/ai-api.md) implements owned chats/runs,
admission, accounting, cancellation and deletion. Bounded recovery and 30-day cleanup
with minimal replay/context receipts are implemented. AI-02 adds an optional [OpenRouter catalog and encrypted personal connections](docs/development/ai-connections.md),
implemented locally but unactivated. [AI-03 source reads](docs/development/ai-03.md)
add lexical search, pages/material excerpts, resolved calendar and typed database
queries with current-source context. RAG and planning remain not implemented; see [the implemented subset](docs/development/ai-setup.md)
and [final AI-01 verification](docs/development/ai-01-execution-plan.md#13-final-ai-01-verification-2026-10-24).

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
workspace (user organization; database/property/record/view schemas)
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
Status: backend authentication is implemented, including email/password flows,
Google OIDC login, safe automatic linking and explicit password-confirmed linking.
[ADR 0008](docs/adr/0008-require-completed-registration.md) requires verified canonical
email and an Ukladen password before application access. Google Gmail/Workspace
proof replaces our verification email; third-party Google email requires fresh
mailbox proof. Existing unverified accounts are never silently claimed. Authentication
email delivery uses the existing Celery worker and a configurable SMTP adapter;
the deployment supplies its SMTP service. Browser email verification and email/password
login/registration, Google login/linking and email password recovery UI are implemented. See
[backend architecture](docs/architecture/backend.md) for current runtime details.

## 5.2 users

```text
profile
timezone
locale
preferences
account state
```

## 5.3 academics

Own academic group/subgroup selection, verified public context and directories.
Term/subject labels are source metadata, not mandatory user organization or invented
stable subject identities. Private student-specific academic records are a conditional
future capability requiring a verified account/API contract.

Status: public reads and academic profiles implemented; private account data not implemented.

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

Status: backend personal events, per-user overrides and resolved calendar reads are
implemented; see [calendar contracts](docs/development/calendar.md). Free-slot/conflict
queries and task blocks are not implemented. The frontend supports weekly resolved
reads and personal-event create/edit/delete. User tags and
collections and saved calendar views are implemented in workspace. All-day/recurring
personal events remain not implemented. Nonblocking database-date projections and
`GET /api/v1/calendar/display` are implemented; see [database contracts](docs/development/databases.md).
Saved views filter authorized resolved events without changing this module's HTTP
contracts or busy flags; see [saved calendar views](docs/development/calendar-views.md).

Calendar composition is presentation over independently owned typed data. Page dates
and task deadlines do not automatically block time. Availability must use the complete
resolved busy set, not a visual filter, and retain source freshness/coverage warnings.
See [workspace architecture](docs/architecture/workspace.md).

## 5.6 tasks

Status: not implemented. Tasks are independent typed objects; ordinary note
checkboxes/database rows do not synchronize them. Deterministic planning is a task
application service using calendar-owned availability, not business logic in an LLM.

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

Status: one-shot reminders for personal and authorized official calendar events are
implemented, backend only. PostgreSQL owns triggers/state; Celery/Beat performs
replay-safe due scans and target revalidation. See [reminder contracts](docs/development/reminders.md).
Task/deadline targets remain not implemented pending P-06. Target capabilities:

```text
task reminders
calendar reminders
deadline reminders
notification scheduling
```

## 5.8 subjects

Status: not implemented. Optional academic organization only.

A user may create separate lecture/lab pages or manually group them, use a template,
or ignore subjects. `subject_id` must not become a requirement of notes, tasks or
personal events. Never infer user grouping from equal external subject strings.

Subject templates/catalogues are later slices, not a prerequisite for workspace pages.

## 5.9 notes

Status: implemented, backend only: standalone pages, optional hierarchy, versioned
JSONB documents with text/headings/flat lists/checkboxes/links, optimistic versions
and recoverable branch trash/restore. Existing Markdown is preserved; its API
projection is derived from blocks. See the [notes API](docs/development/notes.md)
and [ADR 0006](docs/adr/0006-use-versioned-page-block-documents.md).
Editor UI is not implemented; search indexes are derived and owned by search.

Page links are optional. Collections/property schemas/views belong to the
workspace boundary, including implemented typed properties and table/calendar database
views. Event time belongs to calendar. See
[workspace architecture](docs/architecture/workspace.md).

## 5.10 materials

Status: implemented, backend only. Private S3 originals, owner-scoped metadata and
bookmarks, quota reservations, recoverable trash, fenced background extraction and
orphan cleanup. Limits: 25 MiB/file and 1 GiB retained originals/user. PDF text,
DOCX, PPTX, TXT and Markdown are supported within parser budgets; OCR, legacy
DOC/PPT conversion and remote-page fetching are not implemented. See
[materials/search contracts](docs/development/materials.md).

## 5.11 relations

Status: implemented, backend only: optional page links/backlinks to personal events
and official occurrences, including retained historical references, plus owner-scoped
page/material attachments. See the [calendar relations API](docs/development/relations.md)
and [material relations API](docs/development/materials.md). Page-page and task links
are not implemented. Unlinking does not delete either endpoint.
Validate both endpoint ownership/access through application interfaces; a generic
type-plus-UUID reference does not by itself provide foreign-key integrity.

Page containment is owned by notes; collection membership/property values by
workspace; dependency graphs by tasks. Do not infer these rules from arbitrary links.

## 5.12 search

Status: basic filtered PostgreSQL full-text search is implemented, backend only,
over authorized untrashed page text and material titles/extracted text. Canonical
ownership, trash and processing state gate results; derived indexes do not own content.
Russian, English and simple configurations are combined with title weighting.
See [search contracts](docs/development/materials.md). Semantic search, embedding
generation, pgvector retrieval and RAG remain not implemented.

## 5.13 ai

Status: AI-00 and offline AI-01 are complete; owned persistence adapters/migrations
are natively tested on disposable PostgreSQL, unapplied to the app.
The default-disabled fake API adds owned admission/accounting, cancellation/deletion,
bounded recovery and 30-day cleanup with minimal replay/context receipts;
see [persistence contracts](docs/development/ai-persistence.md).
AI-02 adds optional real model connections and AI-03 adds [authorized source tools](docs/development/ai-03.md),
including typed database queries and current-source context rebuilding. They are
implemented locally but unactivated. [AI-04](docs/development/ai-04.md) adds streaming chats,
current-source inspection, personal instructions and owner usage with historical price metadata.
[AI-05](docs/development/ai-05.md) adds an optional pinned CPU embedding adapter and
synthetic full-stack hardware proof; no production index or embedding queue is activated.
Semantic retrieval and write actions remain later stages.
Own conversations, personal instructions, proposals/grants and usage as each feature
is delivered; keep SDK/framework types behind
application interfaces. Checkpoint continuity never replaces authorization or commit truth.

```text
LLM provider abstraction
tool registry
RAG orchestration
context building
AI sessions
action confirmation
scoped owner-issued automatic-action permissions
```

## 5.14 notifications

Status: durable owner-scoped in-app inbox, first-read marking and atomic reminder
delivery are implemented, backend only; see [reminder/inbox contracts](docs/development/reminders.md).
Additional channels remain not implemented. Target capabilities:

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

Current IIS scope is public schedule and related context. Deep private integration
is a future plan only: no account connection, credential handling, grade imports or
write-back in current slices. Future private work requires a new phase request and
verified contracts. See [IIS roadmap](docs/integrations/bsuir-iis-roadmap.md).

## 5.16 workspace

Status: collections, tags, typed memberships, forward/reverse lists and saved calendar views implemented,
backend only; see [workspace API](docs/development/workspace.md). Own user-controlled
organization, references, saved calendar-view configuration and recoverable databases,
property schemas/values, page-backed records and saved table/calendar views with
nonblocking date projection. Mixed display uses the calendar application composition
service and a workspace query port implementation. It does not own
page bodies, event time or official facts.

Saved calendar views store bounded per-source collection/tag filters, layout,
sorting and hidden-event preferences in PostgreSQL. Application queries compose
through `CalendarService` and workspace membership persistence in one read snapshot;
they preserve calendar permissions, overrides and source warnings. Filter references
are checked on writes and reads; a deleted reference requires repair rather than
silently broadening results. See the [implemented contract](docs/development/calendar-views.md).

The organization slice adds real owner-scoped services and foreign-key associations.
[ADR 0004](docs/adr/0004-keep-workspace-organization-optional.md) explains the addition.

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

This is a logical target map. Existing business package markers are not implemented
features. `workspace/` now implements collections, tags and membership under modules;
frontend feature directories are introduced with actual UI work.

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
|   |   |   |   |-- workspace/
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

Exact DB schema is defined per implementation slice. The list includes target
entities, not only current tables; see the roadmap for implemented status.

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

Page (implemented, notes-owned)
PageDocument / Block (implemented flat typed content, notes-owned)
Collection / Tag / TypedMembership (implemented, workspace-owned)
Database / PropertyDefinition / DatabaseRecord / SavedView (implemented, workspace-owned)
Material
MaterialChunk

EntityRelation

AISession
AIMessage
```

---

# 9. Main Data Flows

## 9.1 Onboarding

Workspace onboarding can start with a standalone page or personal event without
academic selection. The following optional academic flow enriches the calendar;
it does not create a mandatory subject hierarchy.

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
 +--> optional user-selected links
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
LangChain create_agent + HITL middleware on LangGraph (offline harness implemented)
PostgreSQL checkpoints (owned API integration tested; running app migration pending)
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
structured logging (implemented)
Sentry / Prometheus / Grafana / OpenTelemetry / Langfuse (not implemented; optional later scope)
```

---

# 11. Local Development Deployment

```text
docker compose
|
+-- web
+-- api
+-- worker
+-- material-worker
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
material-worker
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
material-worker x1 (materials queue, concurrency 1)
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
standalone pages, user organization and database views
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
workspace
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

Detailed slices, dependencies and acceptance checks live in
[implementation roadmap](docs/development/implementation-roadmap.md). This order is
planning, not authorization to implement the next phase.

## Phase 0 — foundation

Implemented: repository, Compose, FastAPI/Next.js shell, PostgreSQL/pgvector,
Redis, Celery, SeaweedFS and CI. Infrastructure availability is not AI/RAG support.

## Phase 1 — existing calendar and public university backend

Implemented backend: auth, user/academic profiles, verified public IIS reads,
official schedule storage/sync, personal events and official overrides/resolved reads.
Login/registration, academic-group selection and weekly calendar UI are implemented.

## Phase 2 — independent workspace

Implemented, backend only: standalone pages, optional nesting, recoverable trash,
typed block documents, page/calendar links, collections/tags and typed memberships.
Saved calendar views over resolved events are implemented, backend only.
Table/calendar database views are implemented under Phase 3.
`subjects` is not a prerequisite.

## Phase 3 — user databases and planning

Implemented, backend only, for user databases: recoverable database/property/page-backed
record APIs, saved table/calendar views, date projection, versioned date moves and
additive mixed calendar display. One-shot calendar reminders and durable in-app
notifications are also implemented; see [reminders](docs/development/reminders.md).
See [database delivery status](docs/development/databases.md) and
[ADR 0007](docs/adr/0007-use-page-backed-database-records.md). Typed tasks,
availability/conflicts, explicit work blocks and task/deadline reminders
remain not implemented.
Planning can be requested independently of database features.

## Phase 4 — knowledge and retrieval

Status: general materials, bounded extraction and filtered/full-text search are
implemented, backend only; see [P-08 contracts](docs/development/materials.md).
Embeddings/semantic retrieval remain not implemented. Preserve permissions and
content versions in later retrieval work.

## Phase 5 — AI tools and grounded actions

Status: not implemented. Read/help and recommendations, exact confirmed actions,
then explicitly permitted automatic actions with revocable scopes and idempotent
execution. RAG follows indexing. A calendar-only AI read slice
can be requested earlier; do not force unrelated feature dependencies.

## IIS scope — public now, private later

Current work is verified public schedule/context and evidence-backed public exception
improvements. Private APIs remain unverified, unimplemented and explicitly deferred.
Do not investigate/implement student-account connections or grades during current
slices. A future requested phase can establish those contracts before implementation.

## Later scope

Optional academic templates, sharing, real-time editing, advanced properties,
recurrence/external calendars, exports/mobile apps and production hardening require
separate decisions and requests. See [open decisions](docs/product/open-questions.md).

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
16. Standalone pages/events must not require academic grouping.
17. Views/relations must not duplicate objects, propagate edits or change availability.
18. Read relevant open decisions; do not treat proposed defaults as owner confirmation.
```

---

# 16. Architecture Documents Split

Use existing documents rather than referring agents to nonexistent specifications:

- [Documentation index](docs/README.md): navigation and update rules.
- [Product overview](docs/product/overview.md): goals and current status.
- [Workspace requirements](docs/product/workspace.md): observable acceptance cases.
- [Open decisions](docs/product/open-questions.md): owner choices versus unverified contracts.
- [Workspace architecture](docs/architecture/workspace.md): implemented organization and planned database/view flows.
- [AI architecture](docs/architecture/ai.md): tools, action lifecycle and retrieval.
- [IIS roadmap](docs/integrations/bsuir-iis-roadmap.md): evidence gates and capability status.
- [Implementation roadmap](docs/development/implementation-roadmap.md): slices and checks.
- [Backend architecture](docs/architecture/backend.md) and development guides: current behavior.
- ADRs: accepted boundary decisions; deployment/frontend docs: their actual baseline.

Exact SQL/HTTP schemas are specified for the requested slice alongside migration,
Pydantic/OpenAPI and current-contract documentation. Planned routes/types must be
marked not implemented. Do not duplicate the same product specification in root files.

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
