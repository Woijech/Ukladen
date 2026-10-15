# Saved Calendar Views Backend

Updated: 2026-10-15.
Status: implemented, backend only. This completes the calendar-view part of P-03.
Database table/calendar views and date projections are implemented separately under
[database contracts](databases.md). This P-03 API continues to return event sources only.
Calendar UI is not implemented.

## Ownership and responsibilities

`workspace` owns saved definitions in `workspace_calendar_views`, added by Alembic
`0013_saved_calendar_views`. A definition stores a UUID, owner, name/color, source
filters, layout, sort order, hidden-event preference, version and timestamps.
It stores no event copies, page bodies or busy intervals.

`CalendarViewService` obtains currently authorized resolved events through
`CalendarService`, then applies explicit collection/tag memberships through the
workspace repository. It does not query calendar/schedule ORM tables or call IIS.
Changing events, overrides or memberships is reflected by the next view query.
Historical membership alone does not make an official occurrence visible: the
normal calendar's current profile, subgroup, active-source and range rules apply.

## HTTP contract

All routes are under `/api/v1/workspace/calendar-views`.

| Method | Suffix | Behavior |
| --- | --- | --- |
| POST | empty | Create a saved definition |
| GET | empty | List owned definitions, creation/UUID order |
| GET | `/{id}` | Read an owned definition |
| PATCH | `/{id}` | Edit supplied settings with `expected_version` |
| DELETE | `/{id}?expected_version=N` | Delete settings only |
| GET | `/{id}/events?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD` | Resolve events using saved settings |

Definition lists use `limit` 1–200 (default 100) and `offset` 0–2147483647.
Names/colors use the existing [organization rules](workspace.md): trimmed 1–100
character names, optional lowercase-normalized `#RRGGBB` colors and UUID identities.
Responses omit owner IDs. Browser sessions, Origin/CSRF protection on writes and
`Cache-Control: no-store` apply. Writes lock the canonical active owner in the
caller-owned transaction. Stale edits/deletions return 409; missing and foreign
definitions/references return the same safe 404.

Example creation body:

```json
{
  "name": "Study",
  "color": "#3377cc",
  "sources": [
    {"source": "official"},
    {
      "source": "personal",
      "collection_ids": ["11111111-1111-4111-8111-111111111111"]
    }
  ],
  "layout": "week",
  "sort_order": "asc",
  "include_hidden": false
}
```

The collection UUID in this example must be replaced by an existing owned collection.
This selects all authorized official events plus personal events explicitly in
that collection. It does not implicitly include events linked to member pages.

## Bounded filter and presentation settings

- `sources`: one or two unique source rules, `official` and/or `personal`. Omission
  defaults to both sources without membership filters. An empty list is invalid.
- Each rule has optional `collection_ids` and `tag_ids`, each with at most 20
  distinct UUIDs. IDs must identify owned definitions of the corresponding kind.
- Within each nonempty ID list, matching any selected definition is sufficient.
  Collection and tag conditions combine with AND. The source rules combine with OR.
  Empty/omitted lists impose no restriction for that kind. Unknown fields,
  duplicate sources/IDs, null settings and arbitrary expressions are rejected.
- `layout`: `day`, `week` (default) or `month`. This is a saved UI preference;
  callers still provide the requested dates explicitly.
- `sort_order`: `asc` (default) or `desc`, ordering by resolved start time and
  display ID as a deterministic tie-breaker.
- `include_hidden`: strict boolean, default false. This changes display selection
  only; it never changes hidden/skipped flags or `blocks_time`.

PATCH preserves omitted fields. `color: null` clears the color; other settings
cannot be null. `sources` replaces the entire source-rule list atomically. Empty
patches are invalid. Successful updates increment the definition version, while
event/member edits do not change it.

The events operation returns the existing `CalendarResponse`: `events`, `timezone`,
schedule `source` state and `warnings`. Dates are inclusive local calendar dates
in the current user's timezone, using the existing maximum 366-day range and
overlap rules. Results preserve current overrides, busy flags and source freshness/
coverage warnings, even when filters select no events. Multi-module resolution uses
one PostgreSQL repeatable-read snapshot. No alternate calendar endpoint is changed.

## Reference lifecycle and integrity

Deleting a view removes only its definition. It does not delete collections, tags,
memberships, pages, events or overrides. Removing a membership changes selection
without deleting its target. Source/profile changes use normal calendar access rules.

Source rules are a bounded, application-validated JSONB configuration. PostgreSQL
enforces ownership via the user foreign key, metadata/envelope checks and the
owner/list index; organization UUIDs inside JSONB are not foreign keys. Every create
and PATCH validates kind and ownership through `WorkspaceService`, serialized with
organization writes by the same owner lock. Every event query revalidates all
references in its read snapshot. Deleting a referenced collection/tag retains the
definition and its original filters; subsequent event queries return 409 until the
owner repairs the source rules. GET/PATCH/DELETE of the definition remain available.
An invalid reference is never dropped to broaden a view silently.

Availability/conflict services remain not implemented. Future availability must use
the complete busy set independently of these display filters. Database properties,
date projections, formulas, arbitrary query languages and UI are separate slices.

## Verification

Tests cover API validation, owner isolation, CSRF, versions, rollback, concurrent
edits, dynamic membership filters, source union, sorting, hidden/moved overrides,
freshness warnings, current academic authorization, snapshot consistency, safe
deletion, SQL constraints and preserving migration upgrade/downgrade/metadata checks.
Native checks use disposable PostgreSQL and Redis; no IIS/LLM calls are required.

Verification on 2026-10-15: Ruff, Ruff format, Pyright and Compose configuration
passed. The complete backend suite with disposable PostgreSQL/Redis passed:
1259 passed, 1 optional native S3 avatar-storage test skipped. Migration round trips
and Alembic metadata checks passed, and 216 local links in updated documentation
were validated. No frontend changes, live IIS/LLM calls, running-stack migration,
deployment or push were performed.
