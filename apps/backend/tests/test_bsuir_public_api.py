import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from app.integrations.bsuir.public_api import IisPublicProvider
from app.modules.academics.application.directory import (
    InvalidUniversityRequest,
    UniversityEntityNotFound,
)
from app.modules.academics.application.ports import AcademicProviderUnavailable

FIXTURES = Path(__file__).parent / "fixtures" / "bsuir"


def public_payload(name: str):
    return json.loads((FIXTURES / "public.json").read_text())[name]


@pytest.mark.parametrize(
    "method,path,fixture",
    [
        ("list_teachers", "/employees/all", "employees"),
        ("list_faculties", "/faculties", "faculties"),
        ("list_departments", "/departments", "departments"),
        ("list_specialities", "/specialities", "specialities"),
        ("list_rooms", "/auditories", "auditories"),
    ],
)
def test_directory_contract(method: str, path: str, fixture: str) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://iis.bsuir.by/api/v1" + path
        assert request.method == "GET" and request.headers["accept"] == "application/json"
        assert not request.headers.get("cookie")
        assert request.extensions["timeout"]["read"] == 5
        return httpx.Response(200, json=public_payload(fixture))

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        rows = getattr(IisPublicProvider(client), method)()
        assert len(rows) == len(public_payload(fixture))
        assert rows[0].id == public_payload(fixture)[0]["id"]
        if fixture == "specialities":
            assert rows[0].education_form.id == 2
        if fixture == "auditories":
            assert rows[0].building_number.name == "3 к."
            assert rows[1].department is None and rows[1].note is None


def test_teacher_by_id_resolves_catalogue_without_guessed_detail_endpoint() -> None:
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json=public_payload("employees"))
        )
    ) as client:
        provider = IisPublicProvider(client)
        teacher = provider.get_teacher(501822)
        assert teacher.url_id == "s-nesterenkov" and teacher.departments
        assert provider.list_teachers()[1].middle_name is None
        with pytest.raises(UniversityEntityNotFound):
            provider.get_teacher(999999)


@pytest.mark.parametrize("identifier", [True, 0, -1, 2**63, "501822"])
def test_invalid_identifiers_do_not_call_upstream(identifier) -> None:
    def fail(_: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid identifier reached IIS")

    with httpx.Client(transport=httpx.MockTransport(fail)) as client:
        with pytest.raises(InvalidUniversityRequest):
            IisPublicProvider(client).get_teacher(identifier)


@pytest.mark.parametrize("data", [{}, [None], [{"id": True}], "html", None])
def test_invalid_directory_payload_is_sanitized(data: object) -> None:
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data))
    ) as client:
        with pytest.raises(AcademicProviderUnavailable):
            IisPublicProvider(client).list_teachers()


@pytest.mark.parametrize("failure", ["duplicate_id", "duplicate_slug", "http", "timeout"])
def test_directory_identity_and_upstream_failures(failure: str) -> None:
    rows = public_payload("employees")
    if failure == "duplicate_id":
        rows[1]["id"] = rows[0]["id"]
    if failure == "duplicate_slug":
        rows[1]["urlId"] = rows[0]["urlId"]

    def respond(request: httpx.Request) -> httpx.Response:
        if failure == "timeout":
            raise httpx.ReadTimeout("private request details", request=request)
        return httpx.Response(503 if failure == "http" else 200, json=rows)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(AcademicProviderUnavailable) as error:
            IisPublicProvider(client).list_teachers()
        assert "private" not in str(error.value)


def response_for(request: httpx.Request) -> httpx.Response:
    name = {
        "/api/v1/employees/all": "employees",
        "/api/v1/departments": "departments",
        "/api/v1/schedule": "group_schedule",
        "/api/v1/employees/schedule/s-nesterenkov": "employee_schedule",
        "/api/v1/announcements/employees": "employee_announcements",
        "/api/v1/announcements/departments": "department_announcements",
    }.get(request.url.path)
    if name:
        return httpx.Response(200, json=public_payload(name))
    if request.url.path == "/api/v1/student-groups":
        return httpx.Response(200, json=json.loads((FIXTURES / "groups.json").read_text()))
    if request.url.path.startswith("/api/v1/last-update-date/"):
        return httpx.Response(200, json={"lastUpdateDate": "13.01.2025"})
    if request.url.path == "/api/v1/schedule/current-week":
        return httpx.Response(200, json=2)
    pytest.fail(f"Unexpected IIS request: {request.url}")


def test_complete_schedule_and_announcement_request_contract() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return response_for(request)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        provider = IisPublicProvider(client)
        group = provider.get_group_schedule("353501")
        assert group and group.group and group.group.id == 24066
        assert dict(requests[-1].url.params) == {"studentGroup": "353501"}
        assert group.starts_on == date(2026, 9, 1)
        assert group.schedules and "Суббота" in group.schedules
        lesson = group.schedules["Суббота"][0]
        assert lesson.week_numbers == [1, 2, 3, 4]
        assert lesson.rooms == ["4-4 к."] and lesson.starts_at.hour == 8
        teacher = provider.get_teacher_schedule(501822)
        assert teacher and teacher.teacher and teacher.teacher.id == 501822
        assert provider.get_teacher_schedule_by_url_id("s-nesterenkov") == teacher
        assert teacher.schedules
        announcement_lesson = teacher.schedules["Четверг"][0]
        assert announcement_lesson.announcement and announcement_lesson.subject is None
        assert announcement_lesson.teachers is None and announcement_lesson.note
        page = provider.get_teacher_announcements(501822, date_from=date(2026, 10, 5))
        assert dict(requests[-1].url.params) == {
            "url-id": "s-nesterenkov",
            "page": "0",
            "size": "20",
            "dateFrom": "2026-10-05",
        }
        assert page.number == 0 and page.last and len(page.content) == 2
        assert page.content[0].date == date(2026, 12, 31)
        assert page.content[0].auditory and page.content[0].starts_at
        assert provider.get_teacher_announcements_by_url_id("s-nesterenkov").content == page.content
        assert len(provider.get_department_announcements(20027)) == 2
        assert dict(requests[-1].url.params) == {"url-id": "kaf-poit"}
        for arguments, expected in [
            ({"group_id": 24066}, {"id": "24066"}),
            ({"group_number": "353501"}, {"groupNumber": "353501"}),
        ]:
            assert provider.get_group_update_date(**arguments) == date(2025, 1, 13)
            assert dict(requests[-1].url.params) == expected
        for arguments, expected in [
            ({"teacher_id": 501822}, {"id": "501822"}),
            ({"url_id": "s-nesterenkov"}, {"url-id": "s-nesterenkov"}),
        ]:
            assert provider.get_teacher_update_date(**arguments) == date(2025, 1, 13)
            assert dict(requests[-1].url.params) == expected
        assert provider.get_current_week() == 2


def test_missing_schedule_is_distinct_from_unknown_group() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return (
            response_for(request)
            if request.url.path.endswith("student-groups")
            else httpx.Response(404)
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        provider = IisPublicProvider(client)
        assert provider.get_group_schedule("353501") is None
        with pytest.raises(UniversityEntityNotFound):
            provider.get_group_schedule("000000")
        assert provider.get_teacher_schedule_by_url_id("s-nesterenkov") is None
        assert provider.get_group_update_date(group_id=24066) is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("studentGroupDto", {"id": 999, "name": "353501"}),
        ("startDate", "invalid"),
        ("startDate", "01.01.2029"),
        ("schedules", {"Monday": [{"numSubgroup": True}]}),
    ],
)
def test_bad_full_schedule_is_unavailable(field: str, value: object) -> None:
    data = public_payload("group_schedule")
    data[field] = value

    def respond(request: httpx.Request) -> httpx.Response:
        return (
            httpx.Response(200, json=data)
            if request.url.path.endswith("/schedule")
            else response_for(request)
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(AcademicProviderUnavailable):
            IisPublicProvider(client).get_group_schedule("353501")


@pytest.mark.parametrize("week", [True, "2", None, 0, 5])
def test_current_week_is_strict_and_bounded(week: object) -> None:
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=week))
    ) as client:
        with pytest.raises(AcademicProviderUnavailable):
            IisPublicProvider(client).get_current_week()


@pytest.mark.parametrize("slug", ["../schedule", "s/teacher", "?id=1", "", "https://other.test"])
def test_invalid_teacher_slug_never_reaches_upstream(slug: str) -> None:
    def fail(_: httpx.Request) -> httpx.Response:
        pytest.fail("Unsafe URL identifier reached IIS")

    with httpx.Client(transport=httpx.MockTransport(fail)) as client:
        with pytest.raises(InvalidUniversityRequest):
            IisPublicProvider(client).get_teacher_schedule_by_url_id(slug)


def test_explicit_announcement_pages_preserve_metadata() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert dict(request.url.params) == {"url-id": "s-nesterenkov", "page": "1", "size": "1"}
        data = public_payload("employee_announcements")
        data.update(number=1, size=1, content=data["content"][1:], totalPages=2, last=True)
        return httpx.Response(200, json=data)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        page = IisPublicProvider(client).get_teacher_announcements_by_url_id(
            "s-nesterenkov", page=1, size=1
        )
        assert page.number == 1 and page.total_elements == 2 and len(page.content) == 1


def test_request_strips_injected_client_credentials() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert not request.headers.get("cookie") and not request.headers.get("authorization")
        return response_for(request)

    with httpx.Client(
        transport=httpx.MockTransport(respond),
        cookies={"session": "private"},
        headers={"Authorization": "Bearer private"},
        auth=("private", "private"),
    ) as client:
        provider = IisPublicProvider(client)
        provider.list_groups()
        provider.get_group_schedule("353501")
        provider.list_teachers()
