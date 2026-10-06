from collections.abc import Iterator
from datetime import UTC, datetime
from typing import cast
from unittest.mock import Mock, create_autospec

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, update
from sqlalchemy.orm import Session
from test_auth_http import application as application
from test_auth_http import browser_login, csrf_headers, seed_user
from test_auth_http import browser_settings as browser_settings
from test_auth_http import client as client
from test_auth_http import database as database
from test_auth_http import issued as issued
from test_auth_http import limiter as limiter
from test_auth_http import live_client as live_client
from test_auth_http import login_service as login_service
from test_auth_http import sessions as sessions
from test_auth_login import password_hash as password_hash
from test_auth_sessions import concurrent_engine as concurrent_engine
from test_auth_sessions import settings as settings
from test_bsuir_academics import group_fixture
from test_bsuir_public_api import response_for

from app.integrations.bsuir.public_api import IisPublicProvider
from app.modules.academics.application.ports import AcademicProfileRepository
from app.modules.academics.application.profile import AcademicService
from app.modules.academics.domain.profile import AcademicProfile
from app.modules.academics.presentation.routes import get_academics
from app.modules.auth.application.dto import IssuedSession
from app.modules.auth.presentation.dependencies import get_current_session
from app.modules.users.application.ports import UserAuthentication
from app.modules.users.infrastructure.orm import UserModel

READ_PATHS = [
    "/api/v1/academics/groups/24066",
    "/api/v1/academics/teachers",
    "/api/v1/academics/teachers/501822",
    "/api/v1/academics/faculties",
    "/api/v1/academics/departments",
    "/api/v1/academics/specialities",
    "/api/v1/academics/rooms",
    "/api/v1/schedule/me",
    "/api/v1/schedule/groups/353501",
    "/api/v1/schedule/teachers/501822",
    "/api/v1/schedule/teachers/by-url-id/s-nesterenkov",
    "/api/v1/schedule/teachers/501822/announcements",
    "/api/v1/schedule/teachers/by-url-id/s-nesterenkov/announcements",
    "/api/v1/schedule/departments/20027/announcements",
    "/api/v1/schedule/groups/353501/last-update",
    "/api/v1/schedule/groups/by-id/24066/last-update",
    "/api/v1/schedule/teachers/501822/last-update",
    "/api/v1/schedule/teachers/by-url-id/s-nesterenkov/last-update",
    "/api/v1/schedule/current-week",
]


@pytest.fixture
def public_provider() -> Iterator[IisPublicProvider]:
    with httpx.Client(transport=httpx.MockTransport(response_for)) as client:
        yield IisPublicProvider(client)


@pytest.fixture
def academic_repository(issued: IssuedSession) -> Mock:
    now = datetime.now(UTC)
    repository = create_autospec(AcademicProfileRepository, instance=True)
    repository.get.return_value = AcademicProfile(
        issued.session.user_id, group_fixture(), 1, now, now
    )
    return repository


@pytest.fixture(autouse=True)
def university_reads(
    client: TestClient,
    application: FastAPI,
    public_provider: IisPublicProvider,
    academic_repository: Mock,
) -> None:
    application.state.university_provider = public_provider
    application.state.schedule_provider = public_provider
    users = create_autospec(UserAuthentication, instance=True)
    users.is_active.return_value = True
    service = AcademicService(academic_repository, users, public_provider)
    application.dependency_overrides[get_academics] = lambda: service


@pytest.mark.parametrize("path", READ_PATHS)
def test_all_read_routes_are_connected(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", READ_PATHS)
def test_all_read_routes_require_authentication(
    client: TestClient, application: FastAPI, path: str
) -> None:
    application.dependency_overrides.pop(get_current_session)
    response = client.get(path)
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


def test_current_schedule_uses_owned_profile_and_iso_transport(
    client: TestClient, academic_repository: Mock, issued: IssuedSession
) -> None:
    data = client.get("/api/v1/schedule/me").json()
    assert data["group"]["name"] == "353501" and data["starts_on"] == "2026-09-01"
    lessons = [row for rows in data["schedules"].values() for row in rows]
    assert sorted(row["subgroup"] for row in lessons) == [0, 1]
    assert all(
        row["week_numbers"] and row["starts_at"] and row["subject_full_name"] for row in lessons
    )
    academic_repository.get.assert_called_once_with(issued.session.user_id)
    data = client.get("/api/v1/schedule/groups/353501?subgroup=2").json()
    assert sorted(row["subgroup"] for rows in data["schedules"].values() for row in rows) == [0, 2]
    academic_repository.get.return_value = None
    response = client.get("/api/v1/schedule/me")
    assert response.status_code == 409 and response.json() == {
        "detail": "Select an academic group first."
    }


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/academics/teachers/0",
        "/api/v1/schedule/teachers/-1",
        "/api/v1/schedule/groups/353501?subgroup=0",
        "/api/v1/schedule/teachers/501822/announcements?page=-1",
        "/api/v1/schedule/teachers/501822/announcements?size=101",
        "/api/v1/schedule/teachers/501822/announcements?date_from=invalid",
        "/api/v1/schedule/teachers/by-url-id/bad.slug",
    ],
)
def test_invalid_http_selectors_are_rejected(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 422


def test_unknown_entities_and_upstream_errors_are_distinct(
    client: TestClient, public_provider: IisPublicProvider
) -> None:
    assert client.get("/api/v1/academics/teachers/999999").status_code == 404
    assert client.get("/api/v1/schedule/groups/000000").status_code == 404
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503))) as unavailable:
        public_provider.client = unavailable
        response = client.get("/api/v1/schedule/current-week")
        assert response.status_code == 503 and response.json() == {"detail": "Service unavailable."}
        assert response.headers["cache-control"] == "no-store"


def test_openapi_documents_every_read_route(client: TestClient) -> None:
    paths = client.get("/api/openapi.json").json()["paths"]
    assert len([path for path in paths if path.startswith("/api/v1/schedule/")]) == 12
    assert paths["/api/v1/schedule/me"]["get"]["responses"]["200"]
    assert paths["/api/v1/academics/teachers/{teacher_id}"]["get"]["responses"]["200"]


def test_live_onboarding_to_schedule_keeps_network_outside_transactions(
    live_client: TestClient,
    concurrent_engine: Engine,
    password_hash: str,
    public_provider: IisPublicProvider,
) -> None:
    application = cast(FastAPI, live_client.app)
    application.state.academic_provider = public_provider
    application.state.schedule_provider = public_provider
    seed_user(concurrent_engine, "student@example.com", password_hash)
    browser_login(live_client)
    assert live_client.get("/api/v1/schedule/me").status_code == 409
    headers = csrf_headers(live_client)
    assert (
        live_client.patch(
            "/api/v1/academics/me", headers=headers, json={"group_id": 24066, "subgroup": 1}
        ).status_code
        == 200
    )
    transactions: list[str] = []

    def begin(connection):
        transactions.append("begin")

    def commit(connection):
        transactions.append("commit")

    def respond(request: httpx.Request) -> httpx.Response:
        assert transactions[-1] == "commit"
        return response_for(request)

    event.listen(concurrent_engine, "begin", begin)
    event.listen(concurrent_engine, "commit", commit)
    try:
        with httpx.Client(transport=httpx.MockTransport(respond)) as transport:
            public_provider.client = transport
            response = live_client.get("/api/v1/schedule/me")
            assert response.status_code == 200
            assert sorted(
                row["subgroup"] for rows in response.json()["schedules"].values() for row in rows
            ) == [0, 1]
            with Session(concurrent_engine) as database, database.begin():
                database.execute(update(UserModel).values(status="disabled"))
            assert live_client.get("/api/v1/schedule/me").status_code == 401
    finally:
        event.remove(concurrent_engine, "begin", begin)
        event.remove(concurrent_engine, "commit", commit)
