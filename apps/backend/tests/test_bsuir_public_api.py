import json
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
