# Workspace Organization Backend

Updated: 2026-10-12.
Status: collection/tag definitions implemented, backend only. Memberships, reverse
lookups, saved views, user databases and UI are not implemented yet.

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

Downgrade removes collection/tag definitions; it does not remove pages or events.
Migrations and native tests must run against disposable test databases unless a
running-stack deployment is explicitly requested.
