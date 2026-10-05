# Academic Profile API

Status: implemented, backend only.

The academics module selects the university schedule context for the authenticated
student. The [IIS investigation](../integrations/bsuir-iis-investigation.md)
records the verified public JSON contract. No HTML parser, new dependency,
frontend, schedule import or background job was added.

## Endpoints

All endpoints require an active opaque browser session and return
`Cache-Control: no-store`. Ownership comes exclusively from that session.
Unverified active users and Google-only accounts are eligible.

| Endpoint | Behavior |
| --- | --- |
| `GET /api/v1/academics/groups` | Live IIS group catalogue mapped to English field names. |
| `GET /api/v1/academics/groups/{group_id}/context` | Validates a catalogue ID, then returns published schedule availability, observed subgroup choices and read-only period context. |
| `GET /api/v1/academics/me` | Stored academic profile, or HTTP 200 JSON `null` before first selection. No upstream request or timestamp update. |
| `PATCH /api/v1/academics/me` | Creates or updates the stored profile after validation, Origin/CSRF and canonical eligibility checks. Returns HTTP 200 after commit. |

Catalogue group IDs are positive upstream integers. Group names remain strings;
leading zeroes must be preserved. The combined
`speciality_department_education_form_id` is IIS's
`specialityDepartmentEducationFormId`, not an independent speciality identifier.
`course` can be null. Other derived metadata is returned from the catalogue:
faculty ID/name/abbreviation, speciality name/abbreviation and education degree.
The degree code is preserved without inferring its enumeration. Users submit
only `group_id` and optional `subgroup`, never metadata or an owner ID.

Example patch using a group verified during the investigation:

```http
PATCH /api/v1/academics/me
Origin: https://your-configured-origin.example
X-CSRF-Token: <token from GET /api/v1/auth/csrf>
Content-Type: application/json
Cookie: <existing browser cookies>

{"group_id":24066,"subgroup":1}
```

The origin must match `AUTH_ALLOWED_ORIGINS` exactly. Bootstrap the CSRF token
through the existing auth endpoint and include cookies. This illustrative origin
is not a new deployment setting.

Example profile response (timestamps illustrative):

```json
{
  "group": {
    "id": 24066,
    "name": "353501",
    "faculty_id": 20026,
    "faculty_name": "Факультет компьютерных систем и сетей",
    "faculty_abbrev": "ФКСиС",
    "speciality_department_education_form_id": 20657,
    "speciality_name": "Информатика и технологии программирования",
    "speciality_abbrev": "ИиТП",
    "course": 4,
    "education_degree": 1
  },
  "subgroup": 1,
  "created_at": "2026-10-05T00:00:00Z",
  "updated_at": "2026-10-05T00:00:00Z"
}
```

## Selection rules

- A missing profile requires `group_id` to create it. No profile is manufactured
  during registration, login or GET. Subgroup-only patches before selection fail.
- Omitted fields preserve existing values. An explicitly supplied same group with
  omitted subgroup preserves the subgroup. A different group resets an omitted
  subgroup to null; an explicit positive subgroup is validated for the new group.
- `subgroup: null` clears the preference. Null means no subgroup filter is chosen.
  Zero is not a selectable subgroup: IIS uses zero for whole-group lessons.
- Positive subgroup values must occur in the group's current regular lessons or
  exams. Choices are sorted and deduplicated. No fixed maximum of two is assumed.
  These are observed schedule labels, not verified personal enrollment assignments.
- A catalogue group without a published schedule can be selected without a
  subgroup. Context returns `schedule_available: false`, `subgroups: []` and
  `period: null` when the verified group's schedule endpoint returns 404.
- `group_id: null`, empty patches, non-integer/bool IDs, non-positive subgroup
  numbers, invalid selections and unsupported fields are rejected. The transport
  bounds group IDs to signed 64-bit and subgroups to signed 32-bit storage.
- Group IDs are revalidated against the live catalogue when explicitly supplied.
  Positive subgroup-only patches also refresh the group from the catalogue.
  Stored-profile reads and subgroup clearing require no IIS availability.

`GET .../context` returns the same `group` object plus `schedule_available`,
`subgroups` and nullable `period`. Period fields are `term_label`, `period_label`,
`starts_on`, `ends_on`, `exams_start_on` and `exams_end_on`; dates use ISO dates.
Source labels are preserved, e.g. `Осенний`; they are not semester IDs or numeric
semesters. Null source values remain null. Next-term schedules are outside this
slice. No semester field is accepted or frozen in the profile.

Actual schedule filtering/import, recurrence expansion, subject/teacher/room
persistence, next-term handling, synchronization and exception interpretation:
Status: not implemented.

## Storage, transactions and failure behavior

`0005_academics_profile`, following `0004_users_avatar`, creates
`university_groups` and `academic_profiles`. Only selected groups are persisted,
not the full live catalogue. The group ID is the upstream ID. Its metadata snapshot
is refreshed during selection and shared by profiles referencing that group.
Snapshots can become stale; there is no periodic refresh or offline catalogue.
PostgreSQL is authoritative for the chosen group/subgroup.

The profile's primary key is the user UUID with cascading deletion, and its group
is a foreign key. Constraints enforce positive identifiers, nonempty group names,
nullable positive course and nullable positive subgroup. Timestamps are timezone
aware. Upserts preserve `created_at` and set `updated_at` on successful writes.
No auth/user/avatar fields are written. Existing users gain no academic row until
selection. Downgrade removes only the two academic tables, losing selections while
preserving existing user/auth/profile/avatar data.

Routes own transactions. PATCH first reads the canonical profile in a short
transaction, completes IIS validation without a transaction, then locks the active
canonical user and commits the selection in a separate transaction. The user lock
serializes writes even before an academic row exists. A subgroup-only request
returns 409 if another operation changes its group between read and write; reload
and retry. Explicit group selections apply to the current committed profile and
preserve its subgroup only when the selected group is unchanged. Write/commit
failures roll back both selected metadata and profile writes.

The IIS adapter reuses the lifespan-managed HTTP client, calls only the verified
HTTPS host, follows no redirects, and uses three-second connect/five-second
read/write/pool timeouts. No retries, cache or scraper is installed. It validates
JSON types, duplicate catalogue identities, schedule group identity, subgroup
numbers and period dates; HTTP/network/malformed-data failures are sanitized.
There is no automatic clearing of an existing choice after an upstream change.

| Status | Meaning |
| --- | --- |
| `200` | Catalogue/context/profile read or committed profile update. |
| `401` | Missing/invalid session or missing/disabled canonical user; auth clears its cookie. |
| `403` | PATCH lacks valid CSRF cookie/header or exact allowed Origin. |
| `409` | Group changed while a subgroup-only operation was preparing. |
| `422` | Invalid transport (`Invalid request.`) or group/subgroup selection (`Invalid academic selection.`). |
| `503` | IIS unavailable/malformed or database/commit failure (`Service unavailable.`). |

No request values, connection strings, upstream bodies or exception details appear
in error responses. Missing schedule 404 is empty context; upstream authorization,
rate limiting, redirects and server errors are failures, not empty context.

## Verification

Normal tests use captured sanitized JSON excerpts or fake providers and never
contact IIS. `test_academics.py`, `test_bsuir_academics.py`,
`test_academics_persistence.py` and `test_academics_http.py` cover contracts,
ownership, omission/null behavior, group changes, canonical eligibility,
Origin/CSRF, upstream failures, transaction boundaries/rollback, migration
compatibility and user/auth/avatar preservation.

Use the existing `AUTH_TEST_DATABASE_URL` and `AUTH_TEST_REDIS_URL` test settings
with disposable services. Tests create isolated schemas and clean their Redis keys.
Run from `apps/backend`:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
```

Run `docker compose config --quiet` from the repository root. Live IIS verification
is separate from tests; repeat small read-only catalogue/context requests only
when intentionally checking the external contract:

```bash
curl --fail --max-time 10 'https://iis.bsuir.by/api/v1/student-groups'
curl --fail --max-time 10 'https://iis.bsuir.by/api/v1/schedule?studentGroup=353501'
```

Verification on 2026-10-05: backend Ruff, Ruff formatting and Pyright passed;
full pytest with temporary PostgreSQL 18/Redis services reported **877 passed,
1 skipped**. The skipped existing avatar storage integration test requires
`AVATAR_TEST_S3_ENDPOINT` and test bucket credentials, which were not supplied.
Existing FastAPI/Starlette and Alembic deprecation warnings remain. Compose config
and `git diff --check` passed. A separate live adapter run successfully mapped
all 421 IIS groups and verified published group 353501 and unpublished group
350505; routine pytest made no live IIS requests. Frontend checks were not run
because this change is backend only.
