# AGENTS.md

Product name: **Ukladen**. Use `ukladen` for the project/database identifier and
`ukladen-backend` / `ukladen-web` for application packages and images.

## 1. Architectural source of truth

Before making any architecture-affecting changes, read:

- `SYSTEM_ARCHITECTURE.md`
- relevant documents under `docs/architecture/`
- relevant ADRs under `docs/adr/`

`SYSTEM_ARCHITECTURE.md` is the primary architecture contract for the project.

If the current implementation conflicts with the architecture, do not silently change the architecture.
Report the conflict first and propose options.

---

## 2. Project language

Use English for the entire technical project surface:

- filenames and directory names;
- class names;
- function and method names;
- variable names;
- database table and column names;
- API endpoints;
- HTTP DTOs;
- enum values;
- Git branch names;
- Git commit messages;
- technical documentation;
- README files;
- architecture documentation;
- implementation plans;
- code comments;
- docstrings;
- test names.

User-facing product text may initially be Russian.

Example:

```python
class CalendarService:
    async def get_free_slots(...):
        """
        Returns available user time slots based on schedule,
        personal events and user-defined overrides.
        """
```

Do not mix Russian technical identifiers into source code.

Bad:

```python
def poluchit_svobodnoe_vremya():
    ...
```

Good:

```python
def get_free_slots():
    ...
```

---

## 3. Architecture style

The backend is a **Modular Monolith**.

Do not create microservices unless explicitly requested through an architecture decision.

Main backend modules:

- `auth`
- `users`
- `academics`
- `subjects`
- `schedule`
- `calendar`
- `tasks`
- `reminders`
- `notes`
- `materials`
- `relations`
- `search`
- `ai`
- `notifications`
- `integrations`

Inside modules, preserve the dependency direction:

```text
presentation -> application -> domain
```

`infrastructure` implements interfaces/ports owned by the application/domain layers.

---

## 4. Backend rules

Primary backend stack:

- Python
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic
- PostgreSQL
- Redis
- Celery

Business logic must not live inside FastAPI route handlers.

Do not write raw SQL inside HTTP handlers.

Every database schema change must be implemented through Alembic migrations.

Do not return SQLAlchemy ORM models directly from the API.

Use Pydantic schemas/DTOs at transport boundaries.

---

## 5. Domain layer

The domain layer must not import:

- FastAPI;
- SQLAlchemy;
- Redis;
- Celery;
- httpx;
- S3 SDKs;
- LLM SDKs;
- concrete external API clients.

The domain layer should contain business entities, rules, value objects and domain errors.

---

## 6. External integrations

Every external API must be isolated behind an adapter/interface boundary.

Do not invent undocumented external API contracts.

If integration information is missing:

1. define an interface;
2. create a fake/stub implementation when needed;
3. add a clear `TODO`;
4. explicitly report the missing contract.

This rule is especially important for BSUIR IIS.

---

## 7. AI

The LLM must never access PostgreSQL directly.

AI functionality must use application tools/services.

Example:

```text
LLM
 |
 v
Tool Registry
 |
 +-> CalendarService
 +-> TaskService
 +-> SearchService
 +-> MaterialService
```

Do not hard-code the business layer to one specific LLM provider.

---

## 8. Redis and Celery

Redis is used for:

- Celery broker;
- cache;
- rate limiting;
- distributed locks;
- idempotency keys;
- temporary state.

Redis is not authoritative storage for user data.

Celery is used for:

- schedule synchronization;
- file processing;
- embedding generation;
- RAG indexing;
- notifications;
- reminders;
- heavy background jobs.

Background jobs should be idempotent where possible.

---

## 9. Files

Binary files must be stored in S3-compatible object storage.

Use SeaweedFS for local/development environments (see `docs/adr/0001-use-seaweedfs.md`).

PostgreSQL should store only metadata, ownership, storage key, processing status and relations.

Do not store binary file content in PostgreSQL.

---

## 10. Quality requirements

Before completing a task, run all applicable checks.

Backend:

```text
Ruff
Pyright
pytest
```

Frontend:

```text
lint
typecheck
build
tests
```

Also validate:

```text
docker compose config
```

Never claim a check passed unless it was actually executed.

---

## 11. Dependencies

Do not add a major dependency without explaining:

- what problem it solves;
- why the current stack is insufficient;
- what complexity it introduces.

Do not create abstractions only because the system may scale in the future.

An abstraction is justified when it protects a real boundary:

- database;
- external API;
- object storage;
- LLM provider;
- queue;
- domain boundary.

---

## 12. Git

Prefer small, cohesive changes.

Do not modify unrelated files.

Never commit:

- `.env`;
- API keys;
- JWT secrets;
- production credentials;
- private keys.

Use English commit messages.

Examples:

```text
feat(calendar): add personal event service
feat(schedule): add schedule provider interface
fix(tasks): prevent dependency cycles
chore: bootstrap monorepo
```

---

## 13. Documentation

All technical documentation must be written in English.

Documentation must describe the implementation that actually exists.

If functionality is planned but not implemented, mark it explicitly:

```text
Status: not implemented.
```

Do not document planned behavior as if it already exists.

Major architecture changes require an ADR under:

```text
docs/adr/
```

---

## 14. AI coding agent workflow

For any substantial task:

1. inspect the repository;
2. read relevant documentation;
3. summarize understanding;
4. identify ambiguities;
5. provide a concise plan;
6. implement only the requested scope;
7. run verification;
8. update documentation;
9. provide a completion report.

Do not proceed to the next project phase without an explicit request.
