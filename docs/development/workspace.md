# Workspace Organization Backend

Updated: 2026-10-12.
Status: collections, tags, typed memberships, member lists and reverse lookups are
implemented, backend only. Saved views, user databases and UI are not implemented.

Collections and tags are independent personal definitions. No academic profile,
page or event is required. Names are trimmed to 1–100 characters; NUL and invalid
Unicode are rejected. Optional colors use `#RRGGBB` and normalize to lowercase.
Names may repeat; UUIDs determine identity, never matching names.

Both types share `workspace_organizations` with an immutable, constrained `kind`.
They share metadata/lifecycle rules but retain separate public resources. This
table stores no page bodies, events or arbitrary user entities. Migration
`0011_workspace_organizations` adds the table without changing existing data.

All routes use `/api/v1/workspace/{kind}`, where kind is `collections` or `tags`.

| Method | Suffix | Behavior |
| --- | --- | --- |
| POST | empty | Create with `name` and optional `color` |
| GET | empty | List, creation/UUID order, limit 1–200 (default 100), offset >= 0 |
| GET | `/{id}` | Read an owned definition |
| PATCH | `/{id}` | Change supplied `name`/`color` with `expected_version` |
| DELETE | `/{id}?expected_version=N` | Delete definition only |

Omitted PATCH fields are preserved; `color: null` clears color; `name: null` and
empty patches are invalid. Successful edits increment the metadata version.
Stale edits/deletion return 409; missing, foreign and wrong-kind IDs return the same
404. Owner IDs come only from the session. Writes lock the canonical active user
in the caller-owned transaction. Browser sessions, Origin/CSRF and `no-store` apply.

## Memberships and reverse lookups

`target_type` is `page`, `personal` or `official`; personal/official identify calendar
event sources. Both collections and tags accept all three types. PUT verifies the
owned definition and target through the notes/calendar application services. New
memberships require active pages or currently accessible active events. A repeated
valid PUT returns the original membership ID and creation time, without duplicates.

| Method | Route under `/api/v1/workspace` | Behavior |
| --- | --- | --- |
| PUT | `/{kind}/{id}/members/{target_type}/{target_id}` | Add/assign a reference |
| DELETE | `/{kind}/{id}/members/{target_type}/{target_id}` | Remove only this reference; absent reference is also 204 |
| GET | `/{kind}/{id}/members` | List explicit members with current metadata |
| GET | `/pages/{page_id}/{kind}` | List the page's collections or tags |
| GET | `/calendar-events/{source}/{event_id}/{kind}` | List the event's collections or tags |

Lists have bounded `limit`/`offset` as above. Members use creation/UUID order and an
optional `target_type` filter: `page`, `personal`, `official`, or `event` (both calendar
sources). Reverse lists use organization creation/UUID order. Unknown filters fail
with 422. Member DTOs include `membership` and a `target` summary/reference, without
page bodies or owner IDs. Membership writes do not increment the metadata version;
individual PUT/DELETE operations are idempotent and serialized by the owner lock.

Membership is explicit and many-to-many. Adding a parent does not add its children;
linking a page to an event does not add that event to the page's collections/tags.
Collection membership does not assign tags, and assigning a tag does not create a
collection membership. Renaming definitions does not rename targets. Updating
targets is reflected by subsequent member lists rather than editing a stored copy.
Membership has no effect on calendar dates, visibility or busy-time semantics.

Member lists are reference lists, like existing relation backlinks: page trash
preserves membership and returns `trashed_at` metadata; normal notes lists still
exclude trash. Restoring a page restores its normal availability. Existing official
references remain readable after schedule withdrawal or group/subgroup changes.
Calendar resolution returns personal overrides plus `active`, `outside_profile` or
`inactive_source` status. Historical resolution receives only IDs from owned stored
memberships; there is no unrestricted official-event lookup. Historical reverse
lists remain available if either kind has an owned membership, even past the last
pagination offset. Without such a reference, current calendar authorization applies.
Removal remains possible after trash or academic/source changes.

`workspace_memberships` has exactly one non-null typed target. Composite foreign
keys enforce collection/tag owner equality with pages and personal events. Unique
organization/target constraints reject duplicates even under competing inserts.
Deleting a definition cascades only to its memberships; deleting a personal event
or physically purging a page removes its memberships. Page purge has no API yet.
Official-event foreign keys retain historical rows. Multi-module member/reverse
reads share a PostgreSQL repeatable-read snapshot.

Migration `0012_workspace_memberships` adds these references without changing page
documents, existing page/calendar links or events. Downgrading it removes memberships
only; downgrading `0011` also removes definitions. Neither removes target objects.
Migrations and native tests must run against disposable test databases unless a
running-stack deployment is explicitly requested.

Native tests cover mixed membership, both organization kinds, reverse pagination,
explicit nesting/link behavior, isolation/CSRF, rollback, competing edits/inserts,
target deletion during a read, trash and official source/profile history, SQL owner
constraints, cascades and Alembic upgrade/downgrade/metadata consistency.

Verification on 2026-10-12: Ruff, Ruff format, Pyright and Compose configuration
passed. The complete backend suite with disposable PostgreSQL/Redis passed:
1187 passed, 1 optional native S3 avatar-storage test skipped. No live IIS/LLM calls,
frontend changes, running-stack migration or deployment were performed.
