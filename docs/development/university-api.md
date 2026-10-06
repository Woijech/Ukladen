# University directories and schedule reads

Status: implemented. All twelve sections of the public BSUIR IIS JSON API are
covered by backend functions and authenticated Ukladen GET endpoints.
The [verified upstream contract](../integrations/bsuir-iis-public-api.md) records
the documentation differences, request parameters and remaining uncertainties.

## Onboarding to the current schedule

1. Authenticate with the existing browser session.
2. `GET /api/v1/academics/groups` and select a group by its numeric `id`.
3. `GET /api/v1/academics/groups/{group_id}/context` supplies observed subgroup
   choices and source period context.
4. `PATCH /api/v1/academics/me` with `{"group_id":24066,"subgroup":1}` saves the
   selection. Use the existing Origin and CSRF headers; registration itself does
   not require or guess a group. See [academic profiles](academic-profile.md).
5. `GET /api/v1/schedule/me` reads the authenticated user's saved group/subgroup.

The current schedule includes whole-group lessons and the selected subgroup.
Null subgroup means all lessons. The same filter applies to regular lessons,
examinations and next-period lessons. The response preserves notes, announcement
and split flags, week numbers, source labels, rooms, teachers and lesson groups.
Dates are ISO `YYYY-MM-DD`, local source times are `HH:MM:SS`. They are schedule
facts for the BSUIR timetable in Minsk, not expanded calendar event timestamps.

No academic profile returns 409 (`Select an academic group first.`). An existing
catalogue group with no published schedule returns 200 with JSON null. An unknown
teacher, department or group schedule number returns 404. The existing academic
numeric group selectors retain their 422 selection errors. A saved group ID that
no longer matches the live
group returns 409. IIS transport/schema failures return sanitized 503 responses.
Invalid selectors return 422. Reads require an active session and use `no-store`.
External requests run after the profile-read transaction has ended.

## HTTP reads

All paths below are relative to `/api/v1`.

| Path | Result |
| --- | --- |
| `/academics/groups` | Group catalogue |
| `/academics/groups/{group_id}` | Group metadata by numeric ID |
| `/academics/groups/{group_id}/context` | Subgroup choices and period |
| `/academics/teachers` | Teacher catalogue |
| `/academics/teachers/{teacher_id}` | Teacher metadata by numeric ID |
| `/academics/faculties` | Faculties |
| `/academics/departments` | Departments, including URL identifiers |
| `/academics/specialities` | Specialities and education form |
| `/academics/rooms` | Rooms, buildings, room types and departments |
| `/schedule/me` | Saved group/subgroup schedule |
| `/schedule/groups/{group_number}` | Group schedule; optional positive `subgroup` query |
| `/schedule/teachers/{teacher_id}` | Teacher schedule by numeric ID |
| `/schedule/teachers/by-url-id/{url_id}` | Teacher schedule by upstream URL identifier |
| `/schedule/teachers/{teacher_id}/announcements` | Teacher announcement page |
| `/schedule/teachers/by-url-id/{url_id}/announcements` | Same page using URL identifier |
| `/schedule/departments/{department_id}/announcements` | Department announcement array |
| `/schedule/groups/{group_number}/last-update` | Update date by group number |
| `/schedule/groups/by-id/{group_id}/last-update` | Update date by group ID |
| `/schedule/teachers/{teacher_id}/last-update` | Update date by teacher ID |
| `/schedule/teachers/by-url-id/{url_id}/last-update` | Update date by URL identifier |
| `/schedule/current-week` | Current academic week, integer 1–4 |

Teacher announcement queries accept `page` (zero-based), `size` (1–100, default
20) and optional ISO `date_from`. Their result contains `content`, `number`,
`size`, `total_elements`, `total_pages`, `last`; callers can fetch subsequent
pages without losing pagination information. Department announcements currently
return an array. Update-date responses contain `{"date":"2025-01-13"}` or a null
date (also for an upstream update-date 404); those dates are source hints, not
reliable monotonic change tokens. URL-based schedule 404 also returns JSON null;
numeric teacher lookup checks the catalogue first.

OpenAPI at `/api/openapi.json` and Swagger at `/api/docs` describe the DTOs and
query/path validation. Technical HTTP field names are English snake_case.

## Backend functions and boundaries

`IisPublicProvider` in `app/integrations/bsuir/public_api.py` implements the
application-owned `UniversityDirectory` and `ScheduleProvider` ports. It also
reuses `IisAcademicProvider` for `list_groups` and `get_context`.

Directory functions: `list_teachers`, `get_teacher`, `list_faculties`,
`list_departments`, `list_specialities`, `list_rooms`.
Schedule functions: `get_group_schedule`, `get_teacher_schedule`,
`get_teacher_schedule_by_url_id`, `get_teacher_announcements`,
`get_teacher_announcements_by_url_id`, `get_department_announcements`,
`get_group_update_date`, `get_teacher_update_date`, `get_current_week`.
Update functions require exactly one of the documented selectors.

Teacher numeric IDs resolve through the live catalogue before URL-based requests.
Department announcement IDs resolve through the current department catalogue.
Group schedules match the live catalogue ID and name. HTTP calls use bounded
timeouts, no redirects and explicitly remove client cookies/Authorization.
Unexpected payloads fail rather than silently manufacturing schedule data.
No additional package dependency, database table, migration or Redis cache was
needed for this read slice.

Calendar event expansion, schedule storage, Celery synchronization, cancellation
and split precedence, personal overrides and calendar UI: **Status: not implemented.**
These require a separate schedule/calendar phase. The existing academic profile
and current-schedule query provide the input for it.

## Verification

Ruff, Ruff format, Pyright and `docker compose config --quiet` passed.
The complete backend suite ran against isolated PostgreSQL 18 and Redis 7.4:
968 passed, one existing SeaweedFS check skipped because dedicated test S3
settings were absent. HTTP checks cover all new reads, authentication, selectors,
safe errors and onboarding through the saved profile into subgroup-filtered
schedule reads. Database checks confirm IIS runs outside the profile transaction
and disabled users cannot read their current schedule.

Live JSON samples also validated the full directory DTOs (761 teachers,
11 faculties, 46 departments, 515 specialities, 317 rooms), teacher schedules,
announcement payloads and their pagination. Normal tests use sanitized fixtures
and HTTPX MockTransport rather than IIS network calls.
