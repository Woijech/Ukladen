# Backend Implementation Roadmap

Updated: 2026-10-15.
Status: implementation roadmap; completed slices are marked below. This document does not authorize starting the
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
| Notes | Standalone pages, typed block documents, Markdown compatibility, nested hierarchy, versions and branch trash | [Notes](notes.md) |
| Relations | Typed page/calendar links, backlinks, atomic linked page creation | [Relations](relations.md) |
| Workspace | Collections, tags, typed membership, forward/reverse lists and saved calendar views | [Workspace](workspace.md), [calendar views](calendar-views.md) |
| Diagnostics | Correlated safe API/worker logs and rotation | [Logging](logging.md) |

Calendar free slots/conflicts, tasks, reminders, general materials,
search, notifications and AI are not implemented. Workspace organization exists;
saved calendar views exist; user databases and page/database views do not.
Authenticated IIS is unverified/unimplemented.
Frontend business flows remain unimplemented apart from browser email verification.

## 3. P-01 standalone pages

Status: implemented, backend only. See [current notes contracts](notes.md).
Dependencies: existing auth/users/persistence only.

Implement in `notes`:

- Standalone owner-scoped page create/read/list/update; no group, subject or event required.
- An explicitly versioned Markdown/text document for the deliberately small first slice.
- Recoverable trash/restore; finalize its policy and limits before implementation.
- UUIDs, timestamps, pagination, expected-version checks and transport validation.
- Alembic migration, database constraints, repository and application service.
- Authenticated DTO endpoints with existing Origin/CSRF and transaction ownership.

The [workspace architecture](../architecture/workspace.md) lists candidate routes.
Resolve the first-slice content limits and trash policy; do not silently claim full
blocks, permanent history, sharing or an editor UI. Nested pages were delivered with this slice.

Done when WS-01 and relevant lifecycle rules pass at service/HTTP/database boundaries,
stale updates and foreign access are rejected, failures roll back, and migration
upgrade/downgrade/metadata checks run only against disposable databases.

## 4. P-02 optional relations

Status: page/calendar links implemented, backend only; see [relations](relations.md).
Page-page knowledge links remain not implemented. Dependencies: P-01 and existing calendar/schedule.

Implement link/unlink/list/backlinks for the actually supported object pairs, starting
with page-calendar-event; page-page links are a later requested slice. Specify personal versus official occurrence
references; validate both endpoints via their module's application interface.

Define duplicate/idempotent behavior, historical source references, unavailable/trashed
endpoints and cleanup. Prefer enforceable typed associations over an unsupported
universal reference table. Neither linking nor unlinking changes event time or content.

Done when WS-03/04/09 and cross-owner/duplicate/unlink-preservation checks pass.
Do not implement task/material relations before those endpoint services exist.

## 5. P-03 user organization and saved calendar views

Status: implemented, backend only — collections, tags, typed memberships and saved
calendar views; see [workspace](workspace.md) and [calendar views](calendar-views.md).
Dependencies: P-01/02 and current calendar. Page/database views remain future P-05 work.

The `workspace` module provides real user-owned tags, collections/membership,
metadata versions, bounded member-type filters and reverse queries. Saved calendar
definitions add versioned name/color, per-source collection/tag filters, layout,
sort direction and hidden-event settings. Event queries reuse authorized resolved
calendar reads with warnings in one database snapshot. Deleted filter references
require explicit repair; view deletion preserves data. Database sources/property
filters and date bindings arrive with P-05.

Official event membership stores a per-user reference, never shared-source preferences.
Filtering and hiding must not remove busy intervals from planning truth. Deleting
collections/views or removing members must preserve pages and events.

Verification covers WS-05, the display/hidden/busy-flag invariants of WS-08 and
permissions/filter validation/lifecycle checks. Availability queries remain P-06.
A backend view API is not a working calendar UI. No generic query language or
user-executable SQL is provided.

## 6. P-04 page hierarchy and block content

Status: implemented, backend only. Hierarchy was delivered with P-01; the subsequent
block slice adds text, headings, flat lists, checkboxes and HTTP/HTTPS links.
See [notes](notes.md) and [ADR 0006](../adr/0006-use-versioned-page-block-documents.md).

Documents use stable UUIDs and ordered, atomic whole-document replacement with the
page version. Validation, legacy Markdown overwrite protection, preserving migration,
concurrent/stale edits and refused destructive downgrade are covered by tests.
Hierarchy moves remain cycle-safe and branch trash retains documents and links.
Nesting and collection membership stay distinct.

Q-08 remains open only for future rich inline formatting, nested blocks and editor
choices. Materials references depend on P-08; export/history/collaboration remain
separate requested slices. This backend API does not implement an editor UI.

## 7. P-05 user databases, properties and calendar projection

Status: in progress; database/property/page-backed record APIs, trash/restore and
typed value/schema conversion and saved table views are implemented. Calendar
database views and date projection are not implemented yet; see [database delivery status](databases.md).
Dependencies: P-01/03/04.
Pages/blocks/databases and table/calendar views are confirmed under Q-01.

Implement database/property/record CRUD, page-backed rows, stable property identities
and type-validated values. Table and calendar views over the same records are required;
list/board views are optional and formulas are deferred. Start with a bounded set of property types and view filters.
Multiple-database membership, recoverable deletion and preserving schema conversion
are defined in [ADR 0007](../adr/0007-use-page-backed-database-records.md).

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
