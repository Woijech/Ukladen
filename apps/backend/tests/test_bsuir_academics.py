import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from app.integrations.bsuir.academics import IisAcademicProvider
from app.modules.academics.application.ports import AcademicProviderUnavailable

FIXTURES = Path(__file__).parent / "fixtures" / "bsuir"


def payload(name: str) -> object:
    return json.loads((FIXTURES / name).read_text())


def test_verified_mapping_and_request_contract() -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "GET"
        assert request.url.host == "iis.bsuir.by"
        assert request.headers["accept"] == "application/json"
        assert not request.headers.get("cookie")
        assert request.extensions["timeout"] == {"connect": 3, "read": 5, "write": 5, "pool": 5}
        return httpx.Response(
            200, json=payload("groups.json" if len(requests) == 1 else "schedule.json")
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        provider = IisAcademicProvider(client)
        groups = provider.list_groups()
        assert len(groups) == 3
        assert next(g for g in groups if g.name == "350505").course is None
        group = next(g for g in groups if g.name == "353501")
        assert (
            group.id,
            group.faculty_id,
            group.speciality_department_education_form_id,
            group.course,
        ) == (
            24066,
            20026,
            20657,
            4,
        )
        context = provider.get_context(group)
        assert context.schedule_available and context.subgroups == (1, 2)
        assert context.period and context.period.term_label == "Осенний"
        assert context.period.starts_on == date(2026, 9, 1)
        assert context.period.exams_end_on == date(2027, 1, 25)
    assert str(requests[0].url) == "https://iis.bsuir.by/api/v1/student-groups"
    assert str(requests[1].url) == "https://iis.bsuir.by/api/v1/schedule?studentGroup=353501"


@pytest.mark.parametrize("status", [403, 429, 500, 302])
@pytest.mark.parametrize("operation", ["groups", "context"])
def test_upstream_http_failures(status: int, operation: str) -> None:
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(status))) as client:
        provider = IisAcademicProvider(client)
        with pytest.raises(AcademicProviderUnavailable):
            if operation == "groups":
                provider.list_groups()
            else:
                provider.get_context(group_fixture())


def group_fixture():
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload("groups.json")))
    ) as client:
        return next(g for g in IisAcademicProvider(client).list_groups() if g.id == 24066)


@pytest.mark.parametrize("error", [httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError])
def test_network_errors_are_sanitized(error: type[httpx.RequestError]) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise error("private upstream details", request=request)

    with httpx.Client(transport=httpx.MockTransport(fail)) as client:
        provider = IisAcademicProvider(client)
        for operation in (provider.list_groups, lambda: provider.get_context(group_fixture())):
            with pytest.raises(AcademicProviderUnavailable) as result:
                operation()
            assert "private" not in str(result.value)


@pytest.mark.parametrize("data", [None, {}, [None], [{"id": True}], "<html>unavailable</html>"])
def test_malformed_catalogue(data: object) -> None:
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data))
    ) as client:
        with pytest.raises(AcademicProviderUnavailable):
            IisAcademicProvider(client).list_groups()


def test_duplicate_group_ids_and_names_are_rejected() -> None:
    groups = json.loads((FIXTURES / "groups.json").read_text())
    for field in ("id", "name"):
        broken = [groups[0], {**groups[1], field: groups[0][field]}]
        with httpx.Client(
            transport=httpx.MockTransport(lambda _, data=broken: httpx.Response(200, json=data))
        ) as client:
            with pytest.raises(AcademicProviderUnavailable):
                IisAcademicProvider(client).list_groups()


@pytest.mark.parametrize(
    "failure", ["identity", "missing", "subgroup", "date", "range", "shape", "html"]
)
def test_malformed_schedule(failure: str) -> None:
    schedule = json.loads((FIXTURES / "schedule.json").read_text())
    if failure == "identity":
        schedule["studentGroupDto"]["id"] = 1
    elif failure == "missing":
        del schedule["schedules"]
    elif failure == "subgroup":
        schedule["schedules"] = {"Понедельник": [{"numSubgroup": True}]}
    elif failure == "date":
        schedule["startDate"] = "31.02.2026"
    elif failure == "range":
        schedule["endDate"] = "01.01.2026"
    elif failure == "shape":
        schedule["exams"] = {}
    else:
        schedule = "<html>unavailable</html>"
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=schedule))
    ) as client:
        with pytest.raises(AcademicProviderUnavailable):
            IisAcademicProvider(client).get_context(group_fixture())


def test_unpublished_schedule_and_nullable_context() -> None:
    group = group_fixture()
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(404))) as client:
        context = IisAcademicProvider(client).get_context(group)
        assert not context.schedule_available and context.subgroups == () and context.period is None
    schedule = json.loads((FIXTURES / "schedule.json").read_text())
    schedule.update(schedules=None, exams=[{"numSubgroup": 3}])
    for field in (
        "currentTerm",
        "currentPeriod",
        "startDate",
        "endDate",
        "startExamsDate",
        "endExamsDate",
    ):
        schedule[field] = None
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=schedule))
    ) as client:
        context = IisAcademicProvider(client).get_context(group)
        assert context.schedule_available and context.subgroups == (3,) and context.period is None
