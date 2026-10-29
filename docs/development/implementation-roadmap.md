# Backend Implementation Roadmap

Updated: 2026-10-28.
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
| Auth | Browser sessions, mandatory verified email/password completion, safe Google linking/mailbox challenges, SMTP/fake delivery | [Backend](../architecture/backend.md), [email](auth-email.md) |
| User | Profile/timezone/locale and private avatar operations | [Profile](user-profile.md), [avatar](user-avatar.md) |
| Academics | Group/subgroup selection and public catalogues/context | [Academic profile](academic-profile.md) |
| University reads | Verified public directory/schedule/announcement reads | [University API](university-api.md) |
| Schedule | Supported expansion, official storage, historical identities, background refresh | [Schedule](schedule.md) |
| Calendar | Personal events, official overrides, resolved range queries | [Calendar](calendar.md) |
| Reminders/notifications | One-shot calendar reminders, durable inbox and replay-safe periodic delivery | [Reminders](reminders.md) |
| Materials/search | Private quota-limited files/bookmarks, page attachments, bounded extraction and PostgreSQL full-text search | [Materials/search](materials.md) |
| Notes | Standalone pages, typed block documents, Markdown compatibility, nested hierarchy, versions and branch trash | [Notes](notes.md) |
| Relations | Typed page/calendar links, backlinks, atomic linked page creation | [Relations](relations.md) |
| Workspace | Collections/tags, typed membership, event views and recoverable page-backed databases with table/calendar views | [Workspace](workspace.md), [calendar views](calendar-views.md), [databases](databases.md) |
| Diagnostics | Correlated safe API/worker logs and rotation | [Logging](logging.md) |

Standalone task create/read/list/update, subtask hierarchy and branch trash are
implemented with a browser UI; see [tasks](tasks.md).
Task dependencies, explicit page links, work sessions/preferences and confirmed
deterministic planning now have local browser controls under [AI-10](ai-10.md).
[Availability](calendar-availability.md) includes personal/official events and
active task sessions, with explicit expected-source coverage limits.
AI-06 semantic retrieval and complete-source analysis are implemented
locally but unactivated.
AI-02 adds optional [OpenRouter models and encrypted connections](ai-connections.md),
implemented locally but unactivated. [AI-04](ai-04.md) adds a locally implemented
streaming chat, source, settings and usage interface; activation remains pending.
The 2026-10-25 follow-up adds an application-owned default model, visible unavailable
catalog choices and a free unlimited access-policy extension point for future user
quotas/subscriptions. Billing and quota persistence remain unimplemented; see the
[catalog/access guide](ai-connections.md). No production activation was performed.
The default-disabled [offline AI API](ai-api.md) provides synthetic chat/run lifecycle
and accounting with bounded execution, overdue-run reconciliation and 30-day physical cleanup.
Workspace organization exists;
saved event views, user databases, table/calendar views and mixed date projection exist.
Authenticated IIS is unverified/unimplemented.
Frontend email/Google login/registration, explicit Google linking, browser email verification and password recovery,
optional academic-group selection, day/week calendar personal-event create/edit/delete
and task management are implemented.
Session isolation, sync-result freshness, full-day interval rendering and explicit
timezone handling have deterministic browser regressions; see
[frontend](../architecture/frontend.md). The separately requested frontend redesign
adds the shared light/dark shell, flat block page editor, materials/search,
collections/tags, database schemas/records/table and day/week/month saved views,
reminders/inbox and profile/avatar settings. Official override editing, saved event
views and mixed projection remain API-only. Tasks share the redesigned navigation,
theme and dialogs. The 2026-10-28 calendar UI follow-up reduces primary navigation
to calendar/notes/tasks with More for other sections, adds contextual event detail
screens and versioned personal-event boundary resizing on the existing calendar API.
No backend phase, official override editor or new relation schema is included. AI-04 UI is implemented locally; AI remains default-disabled.
The P-01–P-08 sections below preserve their original backend-slice scope; their
verification history is not evidence of rerunning backend checks for the UI work.

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
Dependencies: P-01/02 and current calendar. Database views are delivered under P-05.

The `workspace` module provides real user-owned tags, collections/membership,
metadata versions, bounded member-type filters and reverse queries. Saved calendar
definitions add versioned name/color, per-source collection/tag filters, layout,
sort direction and hidden-event settings. Event queries reuse authorized resolved
calendar reads with warnings in one database snapshot. Deleted filter references
require explicit repair; view deletion preserves data. Database sources/property
filters and date bindings are delivered separately under P-05.

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
choices. Material references are implemented in P-08; export/history/collaboration remain
separate requested slices. The separately requested 2026-10-28 frontend slice now
provides a collapsible page tree, breadcrumbs, child creation, a shared slash/plus
block picker, keyboard/native drag reordering and guarded manual saves over this API.
See the [notes capability inventory](notes.md#further-notion-style-capabilities).
Further rich blocks/media require Q-08 schema/rendering decisions; revision retention
requires Q-06; page-page links need typed relations persistence/API. Templates,
import/export and new database views fit existing module boundaries but need their
own concrete scopes/contracts. Comments, sharing/publication, collaboration and
formulas remain separate owner decisions. AI activation and private/external provider
integrations retain their existing authorization and verified-contract gates.

## 7. P-05 user databases, properties and calendar projection

Status: implemented, backend only. Database/property/page-backed record APIs, trash/restore,
typed value/schema conversion, saved table/calendar views, date moves and additive
mixed calendar display are implemented; see [database delivery status](databases.md).
Dependencies: P-01/03/04.
Pages/blocks/databases and table/calendar views are confirmed under Q-01.

Delivered database/property/record CRUD, page-backed rows, stable property identities
and type-validated values. Table and calendar views over the same records are required;
list/board views remain optional and formulas are deferred. The initial property
types, query limits and filters are bounded in the database guide.
Multiple-database membership, recoverable deletion and preserving schema conversion
are defined in [ADR 0007](../adr/0007-use-page-backed-database-records.md).

Implemented explicit date-property view binding and a discriminated calendar display contract.
Projected entries reference their owning record/property; moving them updates that
property via `workspace`. Existing calendar HTTP contracts are preserved.

Done when WS-06/07, property/schema version checks, data-preserving type conversion,
permission-filtered query and date/time edge cases pass. Dates/deadlines are nonblocking
until explicitly scheduled. Formulas, rollups and automatic arbitrary workflows are later.

## 8. P-06 typed tasks and availability

Status: partially implemented — task create/read/list/update, status/priority,
exact deadlines/effort, optimistic versions, owner-scoped subtask hierarchy,
recoverable branch trash, authenticated APIs and task management UI are implemented;
see [task contracts](tasks.md).
Dependencies and explicit page links are now implemented locally in the backend
under [AI-10](ai-10.md), alongside read-only personal/official availability queries.
Browser controls, versioned manual sessions, explicit remaining work, saved weekly
preferences and confirmed deterministic planning/replanning are implemented locally.
Expected IIS coverage remains
explicitly unverified until a verified schedule coverage contract exists.
The owner originally selected manual-only
incremental delivery; the 2026-10-28 owner request now authorizes the full local
AI-10 flow. [Task planning](task-planning.md) describes the implemented local
foundation and AI-07 confirmation bridge. Automatic AI-08 writes remain deferred.
Dependencies: existing calendar; optional page links after P-02.
Can be requested earlier independently of databases. Q-07 is resolved: independent
typed tasks with optional source links and no automatic checkbox/record synchronization.
Future calendar contracts remain Q-05. See [AI planning requirements](../product/ai.md#6-calendar-and-deterministic-planning).

The complete target adds optional links and dependencies to the existing task
fields and recoverable branch trash. Define dependency rules and prevent cycles. Keep typed
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

The selected planning target includes a deterministic task application service,
subtasks/dependencies, structured work windows and editable 45/15-minute session/break
defaults. General replanning protects ordinary personal/official events. Stale/missing
official coverage permits conditional previews only; affected application needs
revalidation. Multi-session plans require atomic all-or-nothing commit/outcomes and
serialization against new busy events. These are requirements, not implemented APIs.

Done when WS-08 and meaningful boundary/DST/ownership/concurrent scheduling checks pass.
Do not force subjects into task creation or reject all intentional event overlaps.

## 9. P-07 reminders and notifications

Status: implemented, backend only, for existing personal and official calendar targets.
See [reminder/inbox contracts and recovery](reminders.md). Task/deadline reminder
targets remain not implemented; basic tasks, hierarchy and trash are delivered under P-06.

Delivered owner-scoped versioned CRUD/cancellation, elapsed-UTC-minute triggers,
durable in-app notifications, idempotent read marking and typed target foreign keys.
Celery/Beat scans PostgreSQL every 30 seconds in bounded batches, revalidates targets
and atomically persists one notification per reminder. Edits/deletions cancel obsolete
work; retries, concurrent sweeps, rollback and broker-gap recovery are covered.
Additional channels/UI/recurrence require separate requested slices and contracts.

## 10. P-08 materials and basic search

Status: implemented, backend only. See [materials/search contracts](materials.md)
for limits, DTOs, migration/recovery rules and dated verification.

Private file reservation/upload/download, bookmarks, optional page attachments,
versioned edits, 30-day trash and periodic S3 cleanup reuse the existing storage
boundary. Owner limits are 25 MiB/file and 1 GiB retained originals/user, with no OCR.
PDF text, DOCX, PPTX, TXT and Markdown use bounded child-process extraction through
the dedicated materials queue/worker. Failed parsing preserves original downloads.

Filtered PostgreSQL full-text retrieval covers canonical page blocks, material titles
and derived file text with immediate owner/trash checks. Native S3, Redis task payloads,
quota races, rollback/cleanup, fenced retries and existing avatar compatibility are
tested. Legacy Office conversion and remote fetching remain not implemented.
Materials UI was delivered separately; chunking, embeddings, semantic retrieval and
full-source AI processing are delivered locally under P-09, with activation pending.
No deployment is performed by this slice.

## 11. P-09 AI help, recommendations, confirmed/automatic actions and RAG

Status: AI-00 and offline AI-01 complete, with a default-disabled fake-only chat/run API and durable
accounting, bounded execution, overdue-run reconciliation, minimal replay/context
receipts and physical cleanup. See [final AI-01 verification](ai-01-execution-plan.md#13-final-ai-01-verification-2026-10-24).
AI-02 implements the optional OpenRouter adapter/catalog and encrypted personal
connections; live account activation remains pending. [AI-03 read tools](ai-03.md)
are implemented locally. [AI-04](ai-04.md) adds streaming chat/settings/usage UI
and supporting APIs. [AI-07](ai-07.md) adds locally implemented exact confirmed actions;
AI-08 automatic writes are deferred indefinitely and application migrations are unapplied.
[AI-10](ai-10.md) adds locally implemented extraction, work settings/sessions and
confirmed deterministic planning with browser controls.
[AI-09 local hardening](ai-09.md) is verified for its historical AI-01–AI-07 subset;
real-model acceptance and application activation remain pending.
[AI-05](ai-05.md) adds a verified optional CPU embedding adapter and disposable
hardware proof with explicit load limits. [AI-06](ai-06.md) implements local versioned indexing, AI-only hybrid retrieval and
durable full-source processing. Activation and real-LLM quality remain pending.
Dependencies: only the application tools actually used; task planning requires P-06.
The [detailed AI plan](ai-implementation-plan.md) splits work into AI-00 through AI-12,
with the [owner-agreed product specification](../product/ai.md),
[tool/fixture contracts](ai-tool-contracts.md) and [connection runbook](ai-setup.md).
Provider-neutral operator models and personal API connections replace the old Groq
baseline. [AI-11](ai-11.md) implements local bounded web fallback and labeled citations;
search activation and live quality remain pending. Selected scope includes chat/usage, RAG, note editing, task extraction,
deterministic planning/replanning, labeled model/web fallback, instructions and
opt-in proactive work. No real provider call or deployment has been performed by the offline slice.
AI calendar reads may be requested before P-08; RAG requires extraction/search.
Execution policies are confirmed under Q-04 and the 2026-10-21 decision table; Q-04a
retains concrete account/grant activation parameters, not unresolved core functionality.

Follow [AI architecture](../architecture/ai.md): provider-neutral adapters and typed
owner-scoped tools. Deliver read/help/recommendations first, exact confirmed writes
second. AI-08 automatic writes are deferred indefinitely by the 2026-10-26 owner
decision; the following grant contract is future reference only. Both write paths require
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
