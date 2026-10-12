# Ukladen Product Overview

Updated: 2026-10-12.
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
[open decisions](open-questions.md). These features are not implemented and are
delivered incrementally rather than all in the first backend slice.

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

Status: not implemented.

Users can create standalone pages, nest pages, edit content, attach materials and
optionally link pages to events, tasks or other pages. The target block document
supports text, headings, lists, checklists, links and attachments incrementally.
A first text-only backend slice must be labelled as such; it is not the full editor.

User-defined databases organize page-backed records with typed properties. Table
and calendar views are mandatory. List/board views are optional later work; formulas
and rollups are deferred. Shared spaces and collaborative editing are not in current scope.

Pages, collections and databases have different roles. A collection is a selected
set of references. A database adds a property schema to its records. Removing a
view or membership must not silently destroy the underlying page.

## 4. Calendar

Implemented, backend only: personal-event CRUD, per-user overrides of official
occurrences and resolved interval reads with source freshness warnings.
See [current calendar API](../development/calendar.md).

Status: not implemented — calendar UI, user tags/colors/saved views, all-day and
recurring personal events, database-record projections, occupied/free intervals,
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

Status: not implemented.

Tasks exist independently of subjects and pages. Targets include status, priority,
optional deadline, effort, dependencies, optional links and explicit calendar blocks.
A deadline and a work block are separate concepts.

Availability considers resolved official occurrences, personal busy events and task
blocks. Skipped lessons and nonblocking entries do not occupy time; hidden busy
entries still do. Missing source coverage remains visible in planning results.

Reminders first produce durable in-app notifications. Additional email, Telegram
and push channels require their own contracts and delivery decisions.

## 8. Materials, search and AI

Status: not implemented, except private avatars using the existing S3 adapter.

Material files belong in S3-compatible storage, with ownership and processing
metadata in PostgreSQL. Processing extracts text, chunks and indexes supported
formats asynchronously. Structured/full-text search precedes semantic search/RAG.

AI answers questions about the user's calendar and workspace, searches content,
explains imported information and proposes edits/plans. It accesses data only
through authorized application tools. Answers based on workspace data identify
supporting records and relevant source freshness.

AI supports reading/help, recommendations, execution after exact confirmation and
explicitly permitted automatic actions. Automatic writes require an owner-issued
scoped permission; otherwise preview and confirmation apply. The specific allowlist,
limits and provider policy remain open. Both paths use normal services, version checks
and durable idempotency. See [AI architecture](../architecture/ai.md).

## 9. Implementation status

| Capability | Current status |
| --- | --- |
| Monolith, Compose, migrations, workers, CI, safe diagnostics | Implemented foundation |
| Browser auth, Google login/linking, email delivery | Implemented backend; email verification UI only |
| User profile/avatar and academic profile | Implemented backend |
| Public IIS directories and live reads | Implemented backend |
| Official schedule storage, supported expansion and sync | Implemented backend with source limitations |
| Personal events, official overrides and resolved calendar | Implemented backend |
| Pages/blocks, relations, collections, tags, databases, views | Status: not implemented. |
| Tasks, availability, reminders and notifications | Status: not implemented. |
| General materials, search, AI and RAG | Status: not implemented. |
| Authenticated IIS capabilities | Status: not implemented; contract unverified. |
| Workspace/calendar business UI | Status: not implemented. |

## 10. Development approach

Implement backend vertical slices with acceptance criteria before UI work is requested.
The next proposed slice is standalone pages, then optional relations and organization.
`subjects` is no longer a prerequisite. The [roadmap](../development/implementation-roadmap.md)
defines dependencies; [open decisions](open-questions.md) record unknowns.

The current scope is personal; shared spaces and simultaneous editing are deferred
by the owner. Additional calendar providers, mobile apps, export/import, formulas
and advanced database features are later work, not first-release requirements.
