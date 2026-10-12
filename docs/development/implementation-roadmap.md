# Backend Implementation Roadmap

Updated: 2026-10-12.
Status: future implementation plan. This document does not authorize starting the
next phase; request a concrete slice before implementing it. Pages/blocks/databases,
mandatory table/calendar views, personal scope and AI execution modes are confirmed.
Formulas, collaboration and private IIS are deferred. Remaining proposed details in
[open decisions](../product/open-questions.md) remain provisional.

## 1. Read order for a development agent

1. `AGENTS.md` and `SYSTEM_ARCHITECTURE.md`.
2. [Product overview](../product/overview.md) and [workspace requirements](../product/workspace.md).
3. [Open decisions](../product/open-questions.md), including questions relevant to the slice.
4. [Workspace architecture](../architecture/workspace.md), or the AI/IIS design as relevant.
5. Current implementation guides for touched modules; inspect code through CodeGraph.
6. The slice below, then a concrete implementation plan covering callers, migrations,
   transport, tests and status updates.

Do not scaffold every future module, build UI during a backend task, or replace
existing services just to match target vocabulary. A package marker is not a feature.

## 2. Existing baseline

| Area | Current implementation | Contract |
| --- | --- | --- |
| Foundation | FastAPI/Next.js shell, Compose, CI, PostgreSQL/pgvector, Redis, Celery, S3 | [Architecture overview](../architecture/overview.md) |
| Auth | Browser sessions, password/email flows, Google login/linking, SMTP/fake delivery | [Backend](../architecture/backend.md), [email](auth-email.md) |
| User | Profile/timezone/locale and private avatar operations | [Profile](user-profile.md), [avatar](user-avatar.md) |
| Academics | Group/subgroup selection and public catalogues/context | [Academic profile](academic-profile.md) |
| University reads | Verified public directory/schedule/announcement reads | [University API](university-api.md) |
| Schedule | Supported expansion, official storage, historical identities, background refresh | [Schedule](schedule.md) |
| Calendar | Personal events, official overrides, resolved range queries | [Calendar](calendar.md) |
| Diagnostics | Correlated safe API/worker logs and rotation | [Logging](logging.md) |

Calendar free slots/conflicts, notes, relations, tasks, reminders, general materials,
search, notifications and AI are not implemented. `workspace` is a planned boundary;
user databases and views do not exist. Authenticated IIS is unverified/unimplemented.
Frontend business flows remain unimplemented apart from browser email verification.

## 3. Recommended next slice: P-01 standalone pages

Status: not implemented. Dependencies: existing auth/users/persistence only.

Implement in `notes`:

- Standalone owner-scoped page create/read/list/update; no group, subject or event required.
- An explicitly versioned Markdown/text document for the deliberately small first slice.
- Recoverable trash/restore; finalize its policy and limits before implementation.
- UUIDs, timestamps, pagination, expected-version checks and transport validation.
- Alembic migration, database constraints, repository and application service.
- Authenticated DTO endpoints with existing Origin/CSRF and transaction ownership.

The [workspace architecture](../architecture/workspace.md) lists candidate routes.
Resolve the first-slice content limits and trash policy; do not silently claim full
blocks, nested pages, permanent history, sharing or an editor UI.

Done when WS-01 and relevant lifecycle rules pass at service/HTTP/database boundaries,
stale updates and foreign access are rejected, failures roll back, and migration
upgrade/downgrade/metadata checks run only against disposable databases.

## 4. P-02 optional relations

Status: not implemented. Dependencies: P-01 and existing calendar/schedule.

Implement link/unlink/list/backlinks for the actually supported object pairs, starting
with page-page and page-calendar-event. Specify personal versus official occurrence
references; validate both endpoints via their module's application interface.

Define duplicate/idempotent behavior, historical source references, unavailable/trashed
endpoints and cleanup. Prefer enforceable typed associations over an unsupported
universal reference table. Neither linking nor unlinking changes event time or content.

Done when WS-03/04/09 and cross-owner/duplicate/unlink-preservation checks pass.
Do not implement task/material relations before those endpoint services exist.

## 5. P-03 user organization and saved calendar views

Status: not implemented. Dependencies: P-01/02 and current calendar.

Introduce the `workspace` module for real user-owned tags, collections/membership and
saved view definitions. Define bounded sources/filters, sorting, names/colors and
supported layout settings. Initial views can operate on existing events/pages;
database property filters arrive with P-05.

Official event membership stores a per-user reference, never shared-source preferences.
Filtering and hiding must not remove busy intervals from planning truth. Deleting
collections/views or removing members must preserve pages and events.

Done when WS-05/08 and permissions/filter validation/lifecycle checks pass. A backend
view API is not a working calendar UI. Do not create a generic query language or
user-executable SQL for the first view slice.

## 6. P-04 page hierarchy and block content

Status: not implemented. Dependencies: P-01; decisions Q-06/08. Personal ownership is confirmed.

Add optional parent/move operations, cycle-safe concurrent mutation behavior and
explicit subtree trash/restore policy. Add a selected versioned block document
contract with stable block IDs, supported payload types, ordering and validation.
Plan a preserving migration from the first text document rather than discarding it.

First block types: text, headings, lists/checklists and links. Materials references
depend on P-08. Rich editor library/JSON format, operations granularity and export
rules must be specified before persistence code; no real-time collaboration assumed.

Done when WS-02, concurrent/stale edits, invalid blocks, moves/cycles and preserving
content migration checks pass. Nesting and collection membership stay distinct.

## 7. P-05 user databases, properties and calendar projection

Status: not implemented. Dependencies: P-01/03/04; remaining decisions Q-05/07/08/12.
Pages/blocks/databases and table/calendar views are confirmed under Q-01.

Implement database/property/record CRUD, page-backed rows, stable property identities
and type-validated values. Table and calendar views over the same records are required;
list/board views are optional and formulas are deferred. Start with a bounded set of property types and view filters.
Finalize whether a page may participate in several databases and document deletion
and schema-conversion behavior before designing tables.

Add explicit date-property view binding and a discriminated calendar display contract.
Projected entries reference their owning record/property; moving them updates that
property via `workspace`. Preserve existing calendar HTTP contracts.

Done when WS-06/07, property/schema version checks, data-preserving type conversion,
permission-filtered query and date/time edge cases pass. Dates/deadlines are nonblocking
until explicitly scheduled. Formulas, rollups and automatic arbitrary workflows are later.

## 8. P-06 typed tasks and availability

Status: not implemented. Dependencies: existing calendar; optional page links after P-02.
Can be requested earlier independently of databases. Decisions: Q-05/07.

Tasks support standalone CRUD, status/priority, optional deadline/effort and optional
links. Define transition/dependency rules and prevent dependency cycles. Keep typed
planning state authoritative; a customizable row is not silently a task.

Add calendar operations:

- `get_occupied_intervals`: resolve the full busy set, include hidden busy entries,
  exclude skipped/nonblocking entries and merge overlapping intervals.
- `get_free_slots`: subtract busy intervals from explicit user availability windows,
  apply minimum duration, timezone/DST and carry source freshness/coverage warnings.
- `check_conflicts`: report interval overlaps; editing excludes the old target interval.
- Task-block lifecycle: explicit time reservations, optional splitting, owner/version
  validation and defined rescheduling/deletion behavior.

Use half-open intervals consistently; touching endpoints do not overlap. Never infer
free time from the currently filtered view or silently treat a missing source as free.

Done when WS-08 and meaningful boundary/DST/ownership/concurrent scheduling checks pass.
Do not force subjects into task creation or reject all intentional event overlaps.

## 9. P-07 reminders and notifications

Status: not implemented. Dependencies: relevant calendar/task target, existing workers.

Implement owner-scoped reminder CRUD and durable in-app notification records. Define
timezone/trigger rules, deduplication, cancellation and retries. Celery/Beat dispatch
due work from PostgreSQL; broker contents are not authoritative reminder storage.

Done when retried jobs do not duplicate notifications, edits/deletions cancel obsolete
deliveries, owner isolation holds and broker interruption has a documented recovery path.
Additional channels need separate adapters/contracts, not guessed integrations.

## 10. P-08 materials and basic search

Status: not implemented. Dependencies: auth, S3/worker foundation; page relations optional.

General material upload/read/link/delete APIs reuse the storage boundary. Define
formats/size limits, ownership, upload-finalization/orphan cleanup and safe URL fetch
rules. Store binaries in S3 and metadata in PostgreSQL. Add processing states and
idempotent extraction jobs for explicitly supported formats.

Add structured/full-text retrieval of authorized pages/material text. Keep permissions
and trash/deletion effective even while derived indexes lag. Make processing failures
visible without deleting the source file. Do not claim arbitrary PDF/OCR support.

Done when native storage and rollback/cleanup/ownership checks plus bounded search
checks pass. Existing avatar APIs must keep working.

## 11. P-09 AI help, recommendations, confirmed/automatic actions and RAG

Status: not implemented. Dependencies: only the application tools actually used.
AI calendar reads may be requested before P-08; RAG requires extraction/search.
Execution modes are confirmed under Q-04; remaining permission/provider policy is Q-04a.

Follow [AI architecture](../architecture/ai.md): provider-neutral adapters and typed
owner-scoped tools. Deliver read/help/recommendations first, exact confirmed writes
second, and explicitly permitted automatic writes third. Both write paths require
expected versions and durable idempotent execution. Automatic mode additionally needs
persisted owner-issued grants, target/operation limits, expiry/revocation and execution
checks; an unconfigured grant must not enable unrestricted writes.

Add cited retrieval, versioned embeddings and RAG after source processing exists.
Use fakes for ordinary tests; enable real provider traffic only after configuration,
cost and content-sharing policy are defined. No direct database or raw IIS tool.

Done when WS-10, confirmation/grant/revocation/replay/stale-target checks, citation
ownership, prompt injection boundaries and provider failure/cancellation handling pass.

## 12. I-01 public IIS scope; I-02 deferred private integration

Q-02 is confirmed: current IIS work is schedule and related public data only.

- I-01: preserve public reads/sync and improve unsupported public exception/identity
  cases only after authoritative evidence. Keep user organization and content separate.
- I-02: future plan, not current work. No private account investigation/connection,
  grade imports, credential storage or private jobs until a new phase is requested.

The [IIS roadmap](../integrations/bsuir-iis-roadmap.md) retains future capability ideas,
all unverified and unimplemented. No guessed APIs or live credentials in tests.
Private write-back remains outside current scope.

## 13. Optional and later work

Subjects/templates come after independent organization and only upon request.
All-day/recurring events, external calendar sync, sharing, real-time collaboration,
advanced formulas/rollups, mobile apps and import/export each need a concrete slice.
They are not hidden requirements of P-01.

## 14. Definition of done for every implementation slice

- Read relevant decisions, specify scope/DTOs/lifecycle, then implement only that slice.
- Complete service, repository, migration, HTTP/auth/CSRF, relevant workers and callers.
- Test meaningful business/security/failure cases with disposable native services where needed.
- Run Ruff, Ruff format, Pyright, pytest and `docker compose config --quiet` for backend changes.
  Run frontend lint/typecheck/build/tests only when frontend is in the requested scope.
- Documentation-only changes need link/status/consistency and diff checks; runtime test
  history is preserved as dated evidence, not reported as rerun without execution.
- Update actual status and contracts, preserving the distinction from planned capabilities.
- Create a cohesive local English commit after verification; push only if requested.
- Report executed checks and any remaining limitations. Stop before the next phase.
