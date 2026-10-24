# Ukladen Product Overview

Updated: 2026-10-25.
Status: target product specification; only capabilities listed as implemented
below exist. Product references describe intent, not feature parity with another app.

## 1. Product direction

Ukladen combines **a Notion-like workspace, a Notion Calendar-like personal calendar,
an AI assistant and deep BSUIR IIS integration** in one product.

The workspace supports academic and personal life equally. Users decide how they
organize pages, events, tasks and materials. Selecting a university group enriches
the calendar; it is not a prerequisite for using the workspace.

There are two complementary entry points: a calendar for time and planned work,
and a workspace for standalone pages, nested content and user-defined organization.
The target includes blocks, user-defined databases/properties and saved views.
The owner confirmed pages, blocks and user-defined databases, with mandatory table
and calendar views. Formulas are deferred. Remaining schema/editor details are in
[open decisions](open-questions.md). Standalone nested pages with flat typed blocks
and Markdown compatibility are implemented, backend only. Database/property/page-backed
record APIs, saved table/calendar views, nonblocking date projection and mixed
calendar display are implemented.
See [database delivery status](../development/databases.md).

## 2. Non-negotiable organization rules

1. A page can exist without an event, subject, collection, database or parent page.
2. A personal event can exist without an academic profile or workspace link.
3. Relations, grouping and academic organization are optional user choices.
4. Imported lectures and laboratories remain separate dated occurrences. Matching
   subject labels never merge them or create shared page content automatically.
5. Editing an event edits that event. Collection membership does not propagate edits.
   Explicit shared-page edits affect that page's content only.
6. A view selects and presents records; it does not own, duplicate or delete them.
7. Visibility and availability are independent: hiding does not free occupied time.
8. Source refreshes preserve user content and organization. Uncertain upstream
   identity is surfaced rather than resolved by guessed subject-name matches.

See [workspace requirements](workspace.md) for examples and acceptance cases.

## 3. Pages and knowledge

Implemented, backend only: standalone nested pages, flat typed blocks, versions and recoverable
branch trash, optional personal/official calendar links, user collections/tags and saved calendar views; see
[notes](../development/notes.md), [relations](../development/relations.md) and
[workspace](../development/workspace.md) and [calendar views](../development/calendar-views.md).

Users can create standalone pages, nest pages, edit text/headings/lists/checkboxes/links
and optionally link pages to events. Block IDs remain stable through edits and order
changes; legacy Markdown is preserved without parsing. Optional material attachments
are implemented; task/page-page links, rich formatting and editor UI remain future work.

User-defined databases organize page-backed records with typed properties. Table
and calendar views are mandatory. List/board views are optional later work; formulas
and rollups are deferred. Shared spaces and collaborative editing are not in current scope.

Pages, collections and databases have different roles. A collection is a selected
set of references. A database adds a property schema to its records. Removing a
view or membership must not silently destroy the underlying page.

## 4. Calendar

Implemented, backend only: personal-event CRUD, per-user overrides of official
occurrences, resolved interval reads with source freshness warnings and optional
page links/backlinks.
See [current calendar API](../development/calendar.md).

Collection/tag names, colors and explicit memberships are implemented in workspace.
Saved calendar views over authorized official/personal events are implemented,
with per-source collection/tag filters and saved layout/sorting preferences.
Database table/calendar views, date projection and versioned date moves are implemented.
The weekly calendar UI and academic-group selection are implemented.
Status: not implemented — per-event colors, all-day and
recurring personal events, occupied/free intervals,
conflict checks and task scheduling blocks.

The target supports day/week/month views, direct editing, moving/resizing, optional
page links and user-selected filters. Imported lessons are initial entries with
source metadata; they do not impose a subject-page hierarchy.

A page's date can make it appear in a calendar view when the user selects that date
property. A deadline/date label is not automatically a meeting or busy interval.
Time blocking requires an explicit event or scheduling decision.

## 5. BSUIR IIS integration

Implemented: public directories and schedule reads, group/subgroup selection,
verified dated expansion, official event persistence and background synchronization.
Official facts and personal overrides remain separate.

The owner confirmed schedule and related public data as current IIS scope. Grades,
curriculum, attendance and other authenticated student-account data are future plans
only. Do not implement or investigate private connections, credentials or write-back
in current slices. Their API contracts remain unverified. See the
[IIS integration roadmap](../integrations/bsuir-iis-roadmap.md).

Retain last valid data during upstream failures, expose sync state and explain
identity/coverage limits. Never claim stale data is complete or infer cancellations,
grades or deadlines from ambiguous text.

## 6. Optional academic organization

Status: not implemented.

`subjects` is an optional academic aid, not the universal parent of workspace data.
Users may organize lectures and labs separately, combine them manually, or ignore
subjects. An explicit import/template can suggest organization only with user choice
and without merging existing records.

No stable subject identifier is established by the current public lesson payload.
External labels remain metadata, not authoritative grouping identities.

## 7. Tasks, planning and reminders

Task create/read/list/update, status/priority, exact deadlines/effort and subtask
hierarchy are implemented with a browser task screen; see [tasks](../development/tasks.md).
Task trash/dependencies/links, work blocks and availability are not implemented.
Calendar reminders and durable
in-app notifications are implemented, backend only; see [reminder contracts](../development/reminders.md).

Tasks exist independently of subjects and pages. The complete target includes status, priority,
optional deadline, effort, dependencies, optional links and explicit calendar blocks.
A deadline and a work block are separate concepts.

Availability considers resolved official occurrences, personal busy events and task
blocks. Skipped lessons and nonblocking entries do not occupy time; hidden busy
entries still do. Missing source coverage remains visible in planning results.

Implemented one-shot reminders target personal or authorized official calendar events,
revalidate their current state and produce durable in-app notifications without duplicates
on job replay. Task/deadline targets depend on P-06. Additional email, Telegram
and push channels require their own contracts and delivery decisions.

## 8. Materials, search and AI

Status: private materials, page attachments and basic search are implemented,
backend only. Files use S3-compatible storage, with ownership and processing metadata
in PostgreSQL. Limits are 25 MiB/file and 1 GiB retained file storage/user. Text PDF,
DOCX, PPTX, TXT and Markdown extraction runs asynchronously without OCR. Bookmarks
store URLs without fetching them. Filtered full-text search covers authorized pages,
material titles and extracted text; see [contracts](../development/materials.md).
Chunking, embeddings, semantic search, AI and RAG remain not implemented.

AI answers questions about the user's calendar and workspace, searches content,
explains imported information and proposes edits/plans. It accesses data only
through authorized application tools. Answers based on workspace data identify
supporting records and relevant source freshness.

AI supports reading/help, recommendations, execution after exact confirmation and
explicitly permitted automatic actions. Automatic writes require an owner-issued
scoped permission; otherwise preview and confirmation apply. The 2026-10-21 policy
selects automatic new-page/task creates only through real scoped grants; concrete
per-grant/account limits remain activation inputs. Both paths use normal services,
version checks and durable idempotency. The editable scenario catalog and planned
owner usage page are specified in [AI product requirements](ai.md), including note
editing, extraction, deterministic planning/replanning, model/web fallback, personal
instructions and opt-in proactive reviews. Provider-neutral operator offerings and
user-owned API connections replace the old single-provider baseline. Delivery and
connection gates are in [the implementation plan](../development/ai-implementation-plan.md).
AI-00 is specified; AI and analytics runtime remain not implemented. See [AI architecture](../architecture/ai.md).

## 9. Implementation status

| Capability | Current status |
| --- | --- |
| Monolith, Compose, migrations, workers, CI, safe diagnostics | Implemented foundation |
| Browser auth, Google login/linking, email delivery | Implemented backend/UI; mandatory email/password completion, safe automatic/explicit Google linking, mailbox proof and password recovery under [ADR 0008](../adr/0008-require-completed-registration.md) |
| User profile/avatar and academic profile | Implemented backend |
| Public IIS directories and live reads | Implemented backend |
| Official schedule storage, supported expansion and sync | Implemented backend with source limitations |
| Personal events, official overrides and resolved calendar | Implemented backend |
| Nested pages, flat typed blocks, Markdown compatibility, recoverable trash, page/calendar links and backlinks | Implemented backend |
| Collections, tags, typed membership and forward/reverse lists | Implemented backend |
| Saved calendar views, source/membership filters and resolved event queries | Implemented backend |
| Database/property/page-backed record APIs with recoverable trash | Implemented backend |
| Saved table views, typed filters/sorts and column selection | Implemented backend |
| Date-bound calendar views, date moves and mixed calendar display | Implemented backend |
| Rich/nested blocks and page-page knowledge links | Status: not implemented. |
| One-shot calendar reminders and durable in-app notifications | Implemented backend |
| Task create/read/list/update, subtask hierarchy, status/priority, exact deadline/effort and versions | Implemented backend and browser UI |
| Task trash/dependencies/links, work blocks, availability and task/deadline reminders | Status: not implemented. |
| Private materials, page attachments and bounded document extraction | Implemented backend; no OCR |
| Filtered PostgreSQL full-text search over pages/materials | Implemented backend |
| Semantic search, AI and RAG | Status: not implemented. |
| Authenticated IIS capabilities | Status: not implemented; contract unverified. |
| Weekly calendar, personal-event create/edit/delete, login/registration and group selection UI | Implemented |
| Workspace pages, saved views, databases and remaining business UI | Status: not implemented. |

## 10. Development approach

Implement backend vertical slices with acceptance criteria before UI work is requested.
Pages, hierarchy and page/calendar links were delivered together at the owner's request.
Block content, user organization and saved calendar views are also implemented.
The requested P-05 backend slice is implemented: database/property/record APIs,
saved table/calendar views, typed filters/sorts, versioned date moves and mixed display.
`subjects` is no longer a prerequisite. The [roadmap](../development/implementation-roadmap.md)
defines dependencies; [open decisions](open-questions.md) record unknowns.

The current scope is personal; shared spaces and simultaneous editing are deferred
by the owner. Additional calendar providers, mobile apps, export/import, formulas
and advanced database features are later work, not first-release requirements.
