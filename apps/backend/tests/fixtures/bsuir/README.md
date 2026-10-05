# Public IIS fixtures

Captured by cookie-free GET on 2026-10-05 from the officially documented
`https://iis.bsuir.by/api/v1/student-groups` and
`https://iis.bsuir.by/api/v1/schedule?studentGroup=353501`.

`groups.json` contains three actual catalogue rows, including nullable course.
`schedule.json` keeps the response root and one actual lesson for each observed
subgroup value 0, 1 and 2. Calendar IDs, teacher emails/photos and other contact
fields were removed. These fixtures are excerpts, not complete schedules.
Tests mutate copies to exercise failures; populated exam cases are synthetic
variants of captured lessons, not a claim of live exam verification.
See `docs/integrations/bsuir-iis-investigation.md` for evidence and limitations.
