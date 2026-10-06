# BSUIR IIS API investigation

Date: 2026-10-05 (Europe/Minsk).
Status: investigation completed before academics implementation.

The subsequent [complete public read investigation](bsuir-iis-public-api.md)
verifies the additional directories, teacher schedules and announcements.
Their backend functions and HTTP reads are now implemented; see
[university API contracts](../development/university-api.md). Calendar recurrence,
storage and synchronization remain unimplemented.

## Method and evidence

Inspected [IIS](https://iis.bsuir.by/) and its official
[API documentation](https://iis.bsuir.by/api) in a JavaScript-capable browser.
Ordinary HTTP GETs to both URLs return the React shell. The rendered API page
contains expandable endpoint documentation and examples, including warnings that
interfaces and access conditions can change without notice. No login was used.

Read the official frontend's public
[main bundle](https://iis.bsuir.by/static/js/main.f83d84ab.js): its Axios base URL
is `https://iis.bsuir.by/api/v1`; schedule selection calls
`/student-groups/filters?name=...`, `/schedule?studentGroup=...` and
`/schedule/current-week`. These are frontend observations, not a guarantee of
those filters' complete contract. Academics can use the documented full catalogue.
The [academic-week page](https://iis.bsuir.by/calendar) displayed 2026–2027,
a repeating four-week cycle and week 2 for October 5–11.

Verified the documented JSON endpoints using small, cookie-free, read-only GETs.
Samples: catalogue, groups `353501` and `310101`, catalogue group `350505`
(which has no published schedule), current week and group update date. No
student account data, credentials or personal schedule were accessed. Examples
below omit calendar identifiers and teacher contact details.

The frontend links [Swagger](https://iis.bsuir.by/api/v1/swagger) for admins.
It redirects to `/api/v1/swagger-ui/index.html`, which returned HTTP 403 without
login. A public machine-readable OpenAPI schema was therefore not verified.
This limits documentation access, not the verified JSON functionality.

## Coverage

All endpoints below use the base URL `https://iis.bsuir.by/api/v1`.
Authentication was unnecessary for the successful sampled public requests.

| Requirement | Endpoint/method/parameters | Evidence and result | Ukladen coverage |
| --- | --- | --- | --- |
| Group catalogue and identifiers | `GET /student-groups`, no parameters | Officially documented; live 200, 421 rows, unique positive integer `id` and unique string `name` in this response | Sufficient for selection; preserve names as strings, including leading zeroes |
| Group metadata | Same catalogue; schedule's `studentGroupDto` | Verified faculty/speciality identifiers, names/abbreviations, `course`, `educationDegree`, `calendarId` | Derive metadata; never ask the student to re-enter it |
| Subgroups | `GET /schedule?studentGroup=353501` (group **name**, not numeric ID) | Documentation defines `numSubgroup=0` as no subgroup; live lessons contain 0, 1, 2 | Positive numbers observed in current lessons/exams form available choices; null preference means all subgroups |
| Period/semester context | Same schedule | Live `currentTerm`, `currentPeriod`, `nextTerm` and period date fields; labels `Осенний`, next term null | Read-only source labels/dates; no verified stable semester ID or numbered semester |
| Regular schedule | Same schedule | Official `schedules` weekday map; 35 and 45 sampled lesson rows | Appears sufficient for future schedule module |
| Recurrence and week numbering | Same schedule plus `GET /schedule/current-week` | Documented lesson `weekNumber`; live arrays in 1–4; current-week live JSON scalar `2` | Four-week cycle supported; arbitrary-date rollover/holiday rules still need schedule-phase verification |
| Date ranges | Same schedule | Root regular/exam bounds and lesson start/end dates, in `DD.MM.YYYY` | Verified bounds support future normalization |
| Exceptions/announcements | Same schedule | Official `dateLesson`, `note`, `announcement`, `split`; documentation says notes can describe moves/languages | Fields available; complete precedence/cancellation rules not verified |
| Examinations/other categories | Same schedule, `exams` | Official example includes consultation/exam; documentation warns correspondence exam sessions also include regular lessons; live sampled `exams=[]` | Appears sufficient, but populated live exam/correspondence examples not verified |
| Subjects | Lesson `subject`, `subjectFullName`, `lessonTypeAbbrev` | Documented and live strings | Labels sufficient; stable subject ID not exposed in sampled rows |
| Teachers | Lesson `employees` | Documented and live arrays, some empty; positive `id`, string `urlId`, names, nullable rank/contact/positions | References sufficient; no need for academics to import teacher data |
| Rooms | Lesson `auditories` | Documented/live string arrays, e.g. `4-4 к.`; API page also documents `GET /auditories` | Room labels sufficient; room-directory response/joins not verified |
| Update signal | `GET /last-update-date/student-group?id=24066` | Documented alternative `groupNumber=353501`; live 200 `{"lastUpdateDate":"13.01.2025"}` | Signal exists, but sampled timestamp predates the 2026 schedule; do not assume complete change detection |

The official page additionally documents lists of faculties, specialities,
departments and teachers, plus teacher schedules and announcements. These are
not required by academics and were not live-tested. No endpoint was inferred
from a guessed name. Schedule investigation does not implement those modules.

## Verified payload details

Catalogue example, with only fields useful for selection:

```json
{
  "id": 24066,
  "name": "353501",
  "facultyId": 20026,
  "facultyName": "Факультет компьютерных систем и сетей",
  "facultyAbbrev": "ФКСиС",
  "specialityDepartmentEducationFormId": 20657,
  "specialityName": "Информатика и технологии программирования",
  "specialityAbbrev": "ИиТП",
  "course": 4,
  "educationDegree": 1
}
```

All 421 rows had `id`, `name`, faculty and speciality fields, degree and
`calendarId`; 11 rows had `course=null`. Degrees observed were 1 and 2, but
their complete enumeration/meaning is not established here. Do not infer the
course from the first digit of a group name. IDs are upstream identities rather
than Ukladen user IDs. Uniqueness is observed in this catalogue; lifetime stability,
ID reuse and group-renaming policy are not officially guaranteed. The adapter
must match schedule `studentGroupDto.id/name` against the catalogue group.

Sanitized current-period excerpt for group 353501:

```json
{
  "studentGroupDto": {"id": 24066, "name": "353501"},
  "employeeDto": null,
  "currentTerm": "Осенний",
  "currentPeriod": "Осенний",
  "nextTerm": null,
  "startDate": "01.09.2026",
  "endDate": "28.12.2026",
  "startExamsDate": "29.12.2026",
  "endExamsDate": "25.01.2027",
  "nextSchedules": null,
  "exams": [],
  "isZaochOrDist": false
}
```

The root also includes `schedules`, a Russian weekday-keyed object of lesson
arrays. A sanitized lesson excerpt:

```json
{
  "numSubgroup": 0,
  "weekNumber": [1, 2, 3, 4],
  "startLessonTime": "08:30",
  "endLessonTime": "09:55",
  "startLessonDate": "05.09.2026",
  "endLessonDate": "26.12.2026",
  "dateLesson": null,
  "subject": "ТОФД",
  "subjectFullName": "Технологии обработки финансовой документации",
  "lessonTypeAbbrev": "ЛК",
  "auditories": ["4-4 к."],
  "note": null,
  "employees": [],
  "announcement": false,
  "split": false
}
```

Teacher `id/urlId` and group nested `name` provide references; no stable subject
ID or room ID appears in sampled lesson rows. The documentation's examples
include nullable note/date/teacher fields and exam lesson date ranges. They are
illustrative and contain comments/trailing commas, not JSON fixtures to parse.

`GET /schedule?studentGroup=350505` returned 404 with an empty body even though
the group exists in the catalogue and has `course=null`. An intentionally
nonexistent group name also returned empty 404. Therefore schedule 404 alone
cannot establish group invalidity: validate against the catalogue first, then
represent absence of a published schedule as empty context. Do not manufacture
subgroups 1 and 2 for such a group. Empty context is distinct from timeout,
HTTP 5xx or malformed JSON, which must be reported as upstream unavailability.

## Limits, caching and synchronization

The verified catalogue response includes `Cache-Control: no-cache, no-store,
max-age=0, must-revalidate`, `Pragma: no-cache`, `Expires: 0` and no observed
ETag/Last-Modified or rate-limit headers. No documented request quota, pagination,
SLA or change-publication guarantee was found. No load/rate-limit probing was
performed. JSON is the verified response format; XML is documented but untested.

Use bounded HTTP timeouts, validate response types/identity and sanitize failures.
Do not add catalogue caching on the strength of undocumented assumptions. Persist
only selected group metadata with the academic profile so normal profile reads do
not depend on IIS; this is a PostgreSQL snapshot, not an offline live catalogue.
The update endpoint's old timestamp means future synchronization should also
compare normalized content rather than relying exclusively on that signal.

## Conclusions and smallest initial contract

**Initial academics: sufficient.** JSON provides valid groups, derived metadata,
observed subgroup numbers and source period labels/date ranges. No parser or
second source is necessary. Users manually choose their group and subgroup;
these are preferences, not a verified IIS enrollment or subgroup assignment.
The public API does not provide a complete authoritative per-group subgroup
registry independent of published lessons. Use observed positive current-lesson
and exam numbers only, or clear the preference when no schedule exists.

**Future schedules: appears sufficient.** Regular/exam data, recurrence, dates,
notes, teacher/room references and an update signal are present. Before that
module, verify populated examinations, correspondence/distance schedules,
exceptions/announcements/split precedence, next-term behavior, arbitrary-date
week numbering and update reliability. Status: not implemented.

**Missing/unverified fields:** no verified stable semester ID, numeric semester,
complete subgroup registry, stable subject/room IDs in lessons, or reliable
monotonic update token. None is required for this initial academics slice.
No freely editable semester field, guessed subgroup maximum, HTML scraping or
additional data source is justified. If future authenticated enrollment requires
student-specific assignment, obtain its official contract then; do not use the
unverified logged-in `/student-groups/user-group-info` interface now.

The first slice should offer an authenticated live catalogue, group context and
current-user profile GET/PATCH. Save numeric upstream group ID plus a selected
metadata snapshot, and an optional positive observed subgroup. A new user has
no academic profile; group selection creates it. Omitted fields preserve values,
explicit subgroup null clears it, and a changed group resets an omitted subgroup.
Group ID null is invalid. Term labels and dates belong to read-only live context,
not user-editable or permanently frozen semester fields. Mutation authentication,
canonical eligibility, Origin/CSRF and route-owned transactions reuse users/auth.
