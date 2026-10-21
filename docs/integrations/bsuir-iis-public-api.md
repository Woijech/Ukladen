# BSUIR IIS public API contract

Verified: 2026-10-05, without login. Scope: all twelve sections of the official
[public API page](https://iis.bsuir.by/api), JSON reads only. Later schedule
verification is recorded below. This is the maintained public integration contract.
Base URL: `https://iis.bsuir.by/api/v1`.

| Operation | Verified request | Observed response |
| --- | --- | --- |
| Groups | `/student-groups` | 421 rows in the sampled catalogue; positive numeric IDs, string names, faculty/speciality metadata, nullable course and degree code |
| Group schedule | `/schedule?studentGroup=353501` | Full schedule; 404 can mean unpublished |
| Teachers | `/employees/all` | 761 teachers, numeric `id`, string `urlId`, names, degree, nullable rank/middle name, photo/calendar links, department labels, `fio` |
| Teacher schedule | `/employees/schedule/s-nesterenkov` | Full schedule, `employeeDto`, null group; announcement lessons can have null subject/type and null employees |
| Faculties | `/faculties` | 11 objects with `id`, `name`, `abbrev` |
| Departments | `/departments` | 46 objects, including `urlId` |
| Specialities | `/specialities` | 515 objects; `educationForm` is an object, despite the documentation's array notation |
| Rooms | `/auditories` | 317 objects; nested type/building/department, nullable capacity, note and department |
| Teacher announcements | `/announcements/employees?url-id=s-nesterenkov` | Spring page envelope, unlike the documented array; content includes ISO dates and optional room/time fields |
| Department announcements | `/announcements/departments?url-id=kaf-poit` | Announcement array; documented `?id=20027` returned 400 |
| Group update date | `/last-update-date/student-group?groupNumber=353501` or `?id=24066` | `lastUpdateDate` in `DD.MM.YYYY`; old dates remain possible |
| Teacher update date | `/last-update-date/employee?id=501822` or documented `?url-id=s-nesterenkov` | Same date envelope |
| Current academic week | `/schedule/current-week` | Integer `2`, four-week cycle |

The official frontend uses the department `url-id` variant and an optional
`dateFrom` filter for employee announcements. A small live request with
`url-id=s-nesterenkov&page=1&size=2&dateFrom=2026-10-05` returned matching
`number=1`, `size=2`, `totalElements=2`, `totalPages=1`, `last=true`.
Preserve page metadata and allow explicit page selection; never silently treat
the first page as the complete list. Department announcement ID lookup must
resolve the current catalogue's `urlId` first.

No direct public teacher-by-numeric-ID detail endpoint is documented. Resolve
the numeric ID through `/employees/all`, then use the verified `urlId` for
schedule/announcements. Do not invent `/employees/{id}`.

Full schedules preserve regular lessons, examinations, next-term lessons,
source period labels and bounds, week numbers, lesson dates/times, notes,
announcement/split flags, teacher/group references and room labels. A selected
subgroup includes whole-group lessons (`numSubgroup=0`) and that subgroup;
null selection includes all. Announcement dates in live responses use ISO format;
lesson and root schedule dates use `DD.MM.YYYY`.

This contract does not establish cancellation/replacement precedence, recurrence for
arbitrary dates, synchronization guarantees or authenticated IIS account APIs.
Observed split-row expansion is verified separately below.
Calendar persistence, personal overrides and background synchronization are implemented
separately; see [schedule](../development/schedule.md) and [calendar](../development/calendar.md).
Private account capabilities remain unverified/unimplemented; see
[deep integration](bsuir-iis-roadmap.md). XML is documented upstream but unverified;
Ukladen requests and validates JSON.

## Group identity, missing schedules and source limits

The initial catalogue/group checks used cookie-free reads of the official rendered
API documentation and JSON endpoints. Samples included groups `353501`, `310101`
and catalogue group `350505`, which had no published schedule. Counts and sampled
values above are dated evidence, not guaranteed current catalogue contents.
The public API documentation renders in JavaScript; its unauthenticated Swagger
link returned 403, so no public machine-readable OpenAPI schema was verified.

Preserve group names as strings, including leading zeroes. Do not derive course,
degree meaning, enrollment or subgroup assignment from a name. Match the returned
schedule's `studentGroupDto.id/name` against the selected catalogue entry. Upstream
ID lifetime stability, reuse and group-renaming policy are not guaranteed.
`specialityDepartmentEducationFormId` is a combined source identifier, not an
independent speciality ID. Source labels do not impose user workspace grouping.

Schedule 404 occurs for both a valid unpublished group and a nonexistent name.
Validate catalogue membership first; then represent unpublished schedules as empty
context, distinct from timeout, HTTP 5xx and malformed JSON. Available subgroup
choices are positive numbers observed in current lessons/exams, not a complete
authoritative registry. Never manufacture subgroup choices for an empty schedule.
Period labels/dates are read-only context; no stable semester ID, numbered semester
or stable subject/room ID in lesson rows was verified. Nullable teacher/note/date
fields and empty teacher arrays are valid. Sanitized excerpts and provenance are
documented in [fixture notes](../../apps/backend/tests/fixtures/bsuir/README.md).

The sampled catalogue prohibited caching and exposed no ETag/Last-Modified or
rate-limit headers. No quota, pagination, SLA or reliable monotonic change token
was established; an update date could predate the schedule. Compare normalized
content rather than trusting that timestamp alone. Store selected group metadata
for profile reads, without treating it as a complete offline catalogue.

The adapter uses bounded socket timeouts, fixed upstream URLs, no credentials or
cookies, no redirects and strict payload/identity validation. Response buffering
currently has no explicit byte/depth budget; establish bounds from verified public
payloads before introducing a potentially incompatible limit. No private-account
contract or load/rate-limit probing is implied by these public observations.

## Schedule expansion verification (2026-10-07)

Read the rendered official API documentation and academic calendar again, and the
public frontend bundle `main.7a86da6b.js`. The calendar's `mo` implementation
numbers Monday-based weeks from the week containing September 1, repeats 1–4,
and continues through January and summer until the next academic year. The
schedule widget advances the week number on Sunday-to-Monday transitions. This
is observed official frontend behavior, not a new documented endpoint contract.
Holiday colors in that calendar do not establish lesson cancellations.

Ukladen expands regular rows by weekday, lesson date bounds (root bounds are a
fallback) and academic week. An explicit `dateLesson` is retained as an exact
date; dated exam/session rows retain their actual lesson type rather than assuming
that every row is an examination. Dated announcements are separate announcement
events. Notes remain source text; they never trigger inferred cancellations.
Next-period recurring rows require their own date bounds. Undated exam rows,
undated announcements and `split=true` fail expansion with a safe unsupported
state: TODO obtain authoritative exception/split rules before implementing them.
The last valid import survives such failures. The verified raw read API still
returns every original field, including unsupported rows.

## Split-row verification (2026-10-16)

This supersedes the split rejection recorded in the historical 2026-10-07 section.
Read the rendered [public API documentation](https://iis.bsuir.by/api), the official
[553501 schedule](https://iis.bsuir.by/schedule/553501), its cookie-free
[JSON response](https://iis.bsuir.by/api/v1/schedule?studentGroup=553501) and public
[frontend bundle](https://iis.bsuir.by/static/js/main.9bfb86fc.js).
Bundle SHA-256: `81c9138d2c73727036102344dfadd34c64b5d060b7c39070a0148976c77b5fe3`.

The official day-list component (`Oi`, byte offset 2387189 in this bundle) selects
rows by explicit lesson date/range and `weekNumber`. It applies no `split` rule.
The official table also displays the sampled split rows: Wednesday laboratory
slots 15:30–16:55 and 17:05–18:30, subgroup 1 on week 1 and subgroup 2 on week 3.
Their ranges are September 2–December 23 and September 16–December 9 respectively.
The four JSON rows expand to 18 independent dated occurrences.

Ukladen therefore applies its existing explicit recurrence/date rules to split rows,
preserving subgroup, time, bounds and original snapshot flags. It does not infer a
replacement/cancellation rule from the flag or notes. This is observed official
client behavior, not a guarantee of every future upstream variant. Invalid/incomplete
rows still fail atomically. Sanitized regression excerpts are in
`apps/backend/tests/fixtures/bsuir/split_lessons.json`; ordinary tests remain offline.
