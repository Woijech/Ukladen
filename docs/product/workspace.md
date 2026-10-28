# Workspace and Calendar Requirements

Updated: 2026-10-25.
Status: target requirements. Calendar, nested pages with flat typed blocks and page/calendar
links, collections/tags and saved calendar views are implemented in the backend; see [notes](../development/notes.md),
[relations](../development/relations.md), [workspace](../development/workspace.md)
and [calendar views](../development/calendar-views.md).
User databases, table/calendar views and mixed date projection are also implemented,
see [database contracts](../development/databases.md).
Remaining capabilities are planned. See [open decisions](open-questions.md) before selecting
remaining editor, membership or calendar details; personal scope is confirmed.
Private materials, optional page attachments and basic full-text search are also
implemented; see [materials/search](../development/materials.md).
The [frontend guide](../architecture/frontend.md) records the delivered block editor,
organization, database views, materials/search and reminder/inbox UI, including its
limits. Saved event views and mixed projection remain API-only.
Tasks support create/read/list/update, status/priority, exact deadlines/effort,
subtask hierarchy and recoverable branch trash in the same browser shell.
Dependencies/links, work blocks and availability remain planned; see
[task delivery](../development/tasks.md).

## 1. Vocabulary

| Concept | Meaning | Required context |
| --- | --- | --- |
| Page | Independent content document; "note" is a user-facing use of a page | Owner only |
| Block | A structured part of a page document | Owning page |
| Event | A dated occurrence with explicit scheduling semantics | Owner for personal events; upstream source for official facts |
| Task | Work to complete; a deadline does not imply an appointment | Owner only |
| Material | An uploaded file or saved external resource | Owner only |
| Relation | An explicit link between independently existing objects | Authorized endpoints |
| Collection | A user-curated set of references, optionally mixing object types | Owner only |
| Tag | A personal label assigned explicitly to pages or events | Owner only |
| Database | A user-defined schema organizing page-backed records | Owner only |
| Property | A typed field defined for a database, such as status or date | Owning database |
| View | Saved source selection, filters, sorting and presentation | Owner and a valid source |
| Subject | Optional academic organization | Explicit user choice |

Collections and databases are user data, not Python modules. A user does not create
a new backend module for "Training". Parent-child page structure is distinct from
ordinary links and collection membership.

## 2. User scenarios and acceptance criteria

### WS-01: A standalone note

The user creates "Ideas" with text and no date, group, subject or collection.

- Create, read and edit work without an academic profile.
- The page is discoverable in the user's page list and basic full-text search.
- Linking it to an event later does not move ownership or change its content.
- A new page does not silently create a calendar event or busy interval.
- Another user cannot list, fetch, modify or link this private page.

### WS-02: A page hierarchy

The user creates "Training" with child pages "Chest" and "Back".

- Root pages are valid; a parent is optional.
- Moving a page preserves its identity, content and external relations.
- A page cannot parent itself or any ancestor; cross-owner nesting is rejected.
- Removing a relation or collection does not reparent the page.
- Parent deletion/trash behavior must follow a documented policy, not cascade
  silently into data loss. See decision Q-06.

### WS-03: Independent lecture and lab

IIS supplies a PBZ lecture and PBZ laboratory on different dates.

- Each occurrence keeps its own identity and local overrides.
- Equal `subject` labels do not create a common page or collection.
- The user can link separate pages, link the same page to both, or link nothing.
- The user can group labs separately from lectures or manually group them together.
- Editing a lab event does not modify the lecture, other labs or linked page text.

The calendar keeps occurrences separate, and optional page/calendar links are
implemented. User-controlled collections and tags with explicit typed membership are implemented.

### WS-04: Direct event editing

The user edits an event's title/time and optionally opens linked content.

- Event edits are addressed by event identity; no subject page is required.
- Personal edits use the personal-event service; imported event edits use the
  per-user override service and never modify shared upstream facts.
- A page link is optional and removable without deleting either endpoint.
- Content changes require a page edit, not a calendar interval update.
- A shared page's content is shared only because the user explicitly linked it;
  it does not propagate event titles, dates or attendance.

### WS-05: Multiple ways to organize the same data

An event appears in "Study" and "This week", with a linked standalone page.

- Membership stores references rather than copied events/pages.
- Removing a membership removes that membership only.
- Deleting a view removes only its settings.
- Renaming a collection or tag does not rename its members.
- Duplicate relation/membership requests have a defined idempotent result.
- Tags and collections are personal; they do not alter official schedule labels.

Collections/tags and membership/reverse APIs are implemented, including safe
deletion and duplicate handling. Saved event views and database table/calendar
views are implemented. Database views have UI; saved event views remain API-only. Membership
does not implicitly include nested pages, linked events or other organization.

### WS-06: User-defined databases

The user creates "Workouts" with properties for muscle group, status and date.

- The user chooses property definitions and available select options.
- A row has its own record identity and references a content page.
- Properties are validated by type; arbitrary JSON is not an alternative to validation.
- Changing a property's type never silently discards existing values.
- Mandatory table and calendar views reference the same records; list/board views are optional.
- Removing a view or record membership does not automatically delete page content.
- No predefined academic fields are mandatory.

The owner confirmed pages, blocks, databases and table/calendar views under Q-01.
Formulas/rollups and unrestricted nesting of database schemas are deferred. AI actions
are a separate scoped capability, not an arbitrary database automation engine.

### WS-07: Calendar presentation of a dated record

The user shows the database's "Planned date" property in a calendar view.

- The date property binding is explicit, not inferred from a property title.
- An undated record remains in its database and is omitted from that calendar view.
- A date-only value retains its calendar date; it is not guessed as midnight UTC.
- A record date or task deadline is nonblocking by default.
- Moving the displayed record updates that bound property, using its own service.
- Scheduling actual work creates/updates an explicit time block; it does not change
  all dated records into busy events.
- Display identities distinguish personal events, official occurrences, record-date
  projections and deadlines. No copied event is manufactured just for rendering.

Database-record date projection and versioned moves are implemented in the backend;
see [database contracts](../development/databases.md). Personal all-day events, task
deadlines and recurrence remain not implemented; their scope stays under Q-05/07.

### WS-08: Independent visibility and availability

The user hides a lesson while planning around a busy appointment.

- View filtering does not remove busy intervals from availability calculations.
- Existing `hidden` official occurrences still block time unless also skipped.
- Existing `skipped` occurrences do not block time, even if visible.
- Merely linking a page or adding a tag never changes availability.
- Source failures, staleness and missing coverage accompany planning results.
- Conflicts can be reported without forbidding intentional overlap.

Hidden/skipped resolution is implemented; availability queries are not implemented.

### WS-09: Synchronization without losing personal work

IIS changes a room/time, withdraws an occurrence or publishes a replacement.

- Refresh does not delete linked user pages, materials, tasks or organization.
- Stable existing event IDs retain their references and overrides.
- Withdrawn/ambiguous references are represented as historical/unavailable links.
- Changed date/subject identity is not matched by guessing. A new occurrence does
  not automatically inherit another occurrence's notes or attendance decision.
- The user can review and explicitly relink a reference if needed.
- Missing external data is distinct from user deletion and from an empty schedule.

Current identity limitations are documented in [schedule storage](../development/schedule.md).
The target improves reconciliation only when a verified contract or explicit user
choice justifies it; it does not claim perfect upstream identity today.

### WS-10: AI understands and acts on the workspace

The user asks about tomorrow, searches a lab note or requests a planning change.

- Read tools use the caller's normal permissions and return source references.
- A question does not mutate data.
- A proposed change names the target object and exact parameters.
- Confirmed execution uses version checks and the normal application service.
- Automatic execution requires an explicit owner grant covering the operation, target
  and limits. Missing/expired/revoked/out-of-scope permissions cannot execute.
- Recommendations do not mutate data; granting one operation never permits all tools.
- Tool retries do not duplicate events/tasks or send repeated notifications.
- Retrieved page/material text cannot grant tool permissions or override instructions.
- AI reports unimplemented tools, stale sources and unsupported IIS capabilities.

AI-01 through [AI-04](../development/ai-04.md) are implemented locally and remain
default-disabled/unactivated. Planning and business-write execution are later stages.
The [AI specification](ai.md) records the 2026-10-21
decisions: independent tasks, labeled effort estimates, explicit work windows,
protected personal events and all-or-nothing confirmed plans. Knowledge fallback
distinguishes missing local evidence from general/web information. Owner instructions
do not grant permissions; proactive work is opt-in. Q-04a now covers concrete account
and grant activation inputs. See [AI architecture](../architecture/ai.md).

## 3. Data lifecycle and editing

User-authored content must have optimistic concurrency protection; stale edits
must not silently replace newer content. Content listing needs bounded pagination.
Transport DTOs expose only authorized fields and document omitted/null semantics.

Pages implement recoverable trash/restore and version-safe whole-document block
replacement. Durable revision history, permanent purge, exports and collaborative
block editing are separate decisions.
Collection deletion, page trash and permanent deletion must never be conflated.
References to unavailable content must not reveal another user's title or body.

## 4. UI intent without prescribing an implementation

Users should be able to open a standalone page, directly edit an event, choose a
view and navigate optional links. "Lecture", "Lab", "Chest" or "Back" are user
organization choices, not required tabs or hard-coded hierarchies.

No UI is implemented by this specification. The backend must support the data and
permissions needed for these choices; widget layouts and editor libraries belong
to a later explicitly requested frontend slice.
