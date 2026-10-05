# BSUIR IIS public API contract

Verified: 2026-10-05, without login. Scope: all twelve sections of the official
[public API page](https://iis.bsuir.by/api), JSON reads only. This supplements the
[academics investigation](bsuir-iis-investigation.md).
Base URL: `https://iis.bsuir.by/api/v1`.

| Operation | Verified request | Observed response |
| --- | --- | --- |
| Groups | `/student-groups` | Group array; see the earlier investigation |
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

This contract does not establish cancellation/split precedence, recurrence for
arbitrary dates, synchronization guarantees or authenticated IIS account APIs.
Calendar persistence, personal overrides and background synchronization remain
separate project phases. XML is documented upstream but has not been verified;
Ukladen requests and validates JSON.
