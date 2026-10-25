# Ukladen Product Overview

Updated: 2026-10-24.
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
and Markdown compatibility are implemented with a flat block editor UI. Database/property/page-backed
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

Implemented in the backend: standalone nested pages, flat typed blocks, versions and recoverable
branch trash, optional personal/official calendar links, user collections/tags and saved calendar views; see
[notes](../development/notes.md), [relations](../development/relations.md) and
[workspace](../development/workspace.md) and [calendar views](../development/calendar-views.md).

Users can create standalone pages, nest pages, edit text/headings/lists/checkboxes/links
and optionally link pages to events. Block IDs remain stable through edits and order
changes; legacy Markdown is preserved without parsing. Optional material attachments
are implemented with UI; task/page-page links and rich formatting remain future work.

User-defined databases organize page-backed records with typed properties. Table
and calendar views are mandatory. List/board views are optional later work; formulas
and rollups are deferred. Shared spaces and collaborative editing are not in current scope.

Pages, collections and databases have different roles. A collection is a selected
set of references. A database adds a property schema to its records. Removing a
view or membership must not silently destroy the underlying page.

## 4. Calendar

Implemented in the backend: personal-event CRUD, per-user overrides of official
occurrences, resolved interval reads with source freshness warnings and optional
page links/backlinks.
See [current calendar API](../development/calendar.md).

Collection/tag names, colors and explicit memberships are implemented in workspace.
Saved calendar views over authorized official/personal events are implemented,
with per-source collection/tag filters and saved layout/sorting preferences.
Database table/calendar views, date projection and versioned date moves are implemented.
The day/week calendar UI, database table/day/week/month views, collections/tags
and academic-group selection are implemented. Saved event views and mixed projection
remain API-only; see the [frontend guide](../architecture/frontend.md).
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

Tasks and availability: status not implemented. Calendar reminders and durable
in-app notifications are implemented with event reminder and inbox UI; see [reminder contracts](../development/reminders.md).

Planned tasks exist independently of subjects and pages. Targets include status, priority,
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
with materials/search UI. Files use S3-compatible storage, with ownership and processing metadata
in PostgreSQL. Limits are 25 MiB/file and 1 GiB retained file storage/user. Text PDF,
DOCX, PPTX, TXT and Markdown extraction runs asynchronously without OCR. Bookmarks
store URLs without fetching them. Filtered full-text search covers authorized pages,
material titles and extracted text; see [contracts](../development/materials.md).
[AI-06](../development/ai-06.md) implements versioned chunk indexing, AI-only hybrid
retrieval and durable complete-source analysis locally; application activation and
real-LLM answer-quality verification remain pending.
[AI-05](../development/ai-05.md) verifies an optional local CPU embedding runtime
used by the optional AI-06 index. AI-02 adds an
optional [OpenRouter catalog and encrypted connections](../development/ai-connections.md),
implemented locally but unactivated. AI-03 adds [authorized source reads](../development/ai-03.md),
including pages, file excerpts, resolved calendar and typed database records.
The default-disabled [offline AI API](../development/ai-api.md) provides synthetic
chats/runs and accounting; it does not read these sources or call a real model.

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
AI-01/02/03 and [AI-04](../development/ai-04.md) are implemented locally, including
streaming chat, source inspection, personal instructions and usage UI. Application
activation and real-provider answer quality remain unverified. See [AI architecture](../architecture/ai.md).

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
| Tasks, availability and task/deadline reminders | Status: not implemented. |
| Private materials, page attachments and bounded document extraction | Implemented backend; no OCR |
| Filtered PostgreSQL full-text search over pages/materials | Implemented backend |
| Offline AI chat/run lifecycle and accounting | AI-01 complete, fake-only and disabled by default; bounded execution/recovery, 30-day cleanup and minimal replay protection; migrations tested only on disposable data |
| Optional real-model catalog and personal API connections | AI-02 backend implemented locally; default-disabled, migration/live activation pending |
| AI workspace/calendar/database reads | AI-03 implemented locally; lexical search, current-source context and historical source references; default-disabled and unactivated |
| Semantic retrieval / full-source analysis | AI-06 implemented locally; unactivated; real-LLM quality unverified. |
| Authenticated IIS capabilities | Status: not implemented; contract unverified. |
| Weekly calendar, personal-event create/edit/delete, login/registration and group selection UI | Implemented |
| Flat block pages, materials/search, collections/tags, database saved views, reminders/inbox and profile/avatar UI | Implemented; see [frontend scope and limits](../architecture/frontend.md) |
| Official override editing, saved event views and mixed calendar display UI | Status: not implemented; backend APIs exist. |
| AI chat/settings/usage UI | Implemented locally under AI-04; default-disabled backend, activation and live-provider quality pending. |
| Tasks UI | Status: not implemented; tasks backend absent. |

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
