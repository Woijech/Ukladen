# Page and Calendar Links

Updated: 2026-10-16.
Status: page/calendar links implemented, backend only. Optional page/material links
are implemented separately in [materials](materials.md). Page-page knowledge links,
task links and database relations are not implemented. Collections/tags and their typed
membership are implemented separately in [workspace](workspace.md).

## Behavior and ownership

A page, including a root/group page, can reference multiple events; an event can
reference multiple pages. Pages and times remain independent. Equal official subject
labels never create or merge links. Use the calendar event's `source` and
`source_event_id`, not its composite display `id`.

`relations` owns `page_calendar_links`. It authorizes endpoints through `NoteService`
and `CalendarService`; all writes share the caller's transaction and active-user
lock. Typed foreign keys enforce page ownership, personal-event ownership and
existence of official occurrences. Migration `0009_page_calendar_links` also adds
an owner-qualified unique constraint to personal events; existing events are retained.

## API

Browser session and `Cache-Control: no-store` apply everywhere; writes require CSRF
and Origin validation. Client-supplied owner IDs are never accepted.

| Method | Path | Behavior |
| --- | --- | --- |
| PUT | `/api/v1/relations/calendar-events/{source}/{event_id}/pages/{page_id}` | Link an existing active owned page |
| POST | `/api/v1/relations/calendar-events/{source}/{event_id}/pages` | Create a page and link it atomically using the notes create DTO |
| DELETE | `/api/v1/relations/calendar-events/{source}/{event_id}/pages/{page_id}` | Unlink without deleting endpoints |
| GET | `/api/v1/relations/calendar-events/{source}/{event_id}/pages` | List owned links and page summaries, including trash state |
| GET | `/api/v1/relations/pages/{page_id}/calendar-events` | List backlinks and current/historical event references |

`source` is `personal` or `official`; all IDs are UUIDs. PUT is idempotent: repeats
return the original link, without duplicate rows or backlinks. DELETE of an absent
or foreign link returns 404. Lists use `limit` 1–200 (default 100), `offset` >= 0,
and stable creation/UUID ordering. Unknown query/transport values follow FastAPI
validation. Responses expose no owner IDs or page bodies, and summary reads do not
load documents. Fetch a page's detail/document for its block content or derived
Markdown. No unbounded recursive tree or implicit descendant links exist.

A client can create an event with the existing calendar POST, then attach its chosen
page with PUT. These are separate operations; event creation and linking are not a
single atomic request. Creating a **new page from an existing event** is atomic:
failed access validation or link persistence leaves no orphan page. The notes create
DTO also accepts a block `document`, mutually exclusive with legacy `content`.

## Lifecycle and official sources

New official links require the current academic group/subgroup and an active stored
occurrence. A personal target must belong to the caller. Missing/foreign endpoints
return 404; linking a trashed page or inactive official occurrence returns 409.

Trashing pages preserves links and exposes the page's trash state; restoration
preserves those links. Unlinking also works while the page is trashed. Personal event
deletion cascades its links only and leaves pages intact. Owner deletion cascades
owned links. Official occurrences retain their historical IDs; synchronization does
not delete notes or relink them by a guessed matching title.

Existing owner-scoped references remain readable/removable after group/subgroup
changes or source withdrawal. Backlinks report `active`, `outside_profile` or
`inactive_source`; withdrawn status takes precedence. Event title/time and hidden/
skipped flags include the caller's official overrides. Historical reads use IDs from
stored owner links, never arbitrary unrestricted HTTP lookup. Paginated reads share
one PostgreSQL repeatable-read snapshot across relations, notes and calendar.

## Verification

Tests cover duplicate and concurrent links, both endpoint owners, CSRF/sessions,
atomic rollback, independent edits, subtree trash/restore, unlink preservation,
personal-event deletion, source refresh/withdrawal, subgroup changes, overridden
reference times, bounded paging, typed constraints and migration round trips.

Verified on 2026-10-12: full backend pytest with disposable PostgreSQL/Redis —
1088 passed, 1 S3 avatar-storage test skipped. Ruff, Ruff format, Pyright,
`docker compose config` and local documentation links passed. No frontend changes
or running-stack migration/deployment were performed.
