from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import Mock, create_autospec
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, event, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_academics import GROUP, OTHER
from test_academics import provider as provider
from test_auth_http import CSRF_COOKIE, SESSION_COOKIE, browser_login, csrf_headers, seed_user
from test_auth_http import application as application
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
from test_users_profile_http import snapshot

from app.modules.academics.application.ports import (
    AcademicProfileRepository,
    AcademicProviderUnavailable,
)
from app.modules.academics.application.profile import AcademicService
from app.modules.academics.domain.profile import AcademicProfile, GroupContext
from app.modules.academics.infrastructure.orm import AcademicProfileModel, UniversityGroupModel
from app.modules.academics.presentation.routes import get_academic_provider, get_academics
from app.modules.auth.application.dto import IssuedSession
from app.modules.auth.infrastructure.orm import IdentityModel, SessionModel
from app.modules.auth.infrastructure.token_service import generate_token, hash_token
from app.modules.auth.presentation.dependencies import get_current_session
from app.modules.users.application.ports import UserAuthentication
from app.modules.users.infrastructure.orm import UserModel

URL = "/api/v1/academics/me"
CATALOGUE = "/api/v1/academics/groups"


@pytest.fixture
def repository(issued: IssuedSession) -> Mock:
    now = datetime.now(UTC)
    profile = AcademicProfile(issued.session.user_id, GROUP, 1, now, now)
    repository = create_autospec(AcademicProfileRepository, instance=True)
    repository.get.return_value = profile
    repository.save.side_effect = lambda user_id, group, subgroup: replace(
        profile, group=group, subgroup=subgroup
    )
    return repository


@pytest.fixture
def users() -> Mock:
    users = create_autospec(UserAuthentication, instance=True)
    users.is_active.return_value = users.lock_active.return_value = True
    return users


@pytest.fixture(autouse=True)
def academics(
    application: FastAPI, repository: Mock, users: Mock, provider: Mock
) -> AcademicService:
    service = AcademicService(repository, users, provider)
    application.dependency_overrides[get_academics] = lambda: service
    application.dependency_overrides[get_academic_provider] = lambda: provider
    return service


def test_contract_missing_profile_and_ownership(
    client: TestClient, repository: Mock, issued: IssuedSession
) -> None:
    response = client.get(URL)
    assert response.status_code == 200 and set(response.json()) == {
        "group",
        "subgroup",
        "created_at",
        "updated_at",
    }
    repository.get.assert_called_with(issued.session.user_id)
    repository.get.return_value = None
    assert client.get(URL).json() is None
    response = client.patch(
        URL, headers=csrf_headers(client), json={"group_id": GROUP.id, "subgroup": None}
    )
    assert response.status_code == 200 and response.json()["group"]["id"] == GROUP.id
    repository.save.assert_called_once_with(issued.session.user_id, GROUP, None)
    schema = client.get("/api/openapi.json").json()
    assert set(schema["paths"][URL]) == {"get", "patch"}
    assert schema["components"]["schemas"]["AcademicProfilePatch"]["additionalProperties"] is False
    assert response.headers["cache-control"] == "no-store"


def test_catalogue_and_context(client: TestClient, provider: Mock) -> None:
    response = client.get(CATALOGUE)
    assert response.status_code == 200 and [r["id"] for r in response.json()] == [
        GROUP.id,
        OTHER.id,
    ]
    response = client.get(f"{CATALOGUE}/{GROUP.id}/context")
    assert response.status_code == 200 and response.json()["subgroups"] == [1, 2]
    assert response.headers["cache-control"] == "no-store"
    provider.get_context.return_value = GroupContext(GROUP, False)
    provider.get_context.side_effect = None
    assert client.get(f"{CATALOGUE}/{GROUP.id}/context").json()["schedule_available"] is False
    assert client.get(f"{CATALOGUE}/1/context").status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"group_id": None},
        {"group_id": "24066"},
        {"group_id": True},
        {"subgroup": 0},
        {"subgroup": 3},
        {"semester": 1},
        {"group_id": GROUP.id, "user_id": str(uuid4())},
    ],
)
def test_invalid_patches_are_safe(
    client: TestClient, repository: Mock, payload: dict[str, object]
) -> None:
    response = client.patch(URL, headers=csrf_headers(client), json=payload)
    assert response.status_code == 422 and "24066" not in response.text
    assert response.headers["cache-control"] == "no-store"
    repository.save.assert_not_called()


@pytest.mark.parametrize("failure", ["origin", "foreign_origin", "header", "cookie", "mismatch"])
def test_csrf_and_origin_protection(client: TestClient, repository: Mock, failure: str) -> None:
    headers = csrf_headers(client)
    if failure == "origin":
        headers.pop("Origin")
    elif failure == "foreign_origin":
        headers["Origin"] = "https://foreign.example"
    elif failure == "header":
        headers.pop("X-CSRF-Token")
    elif failure == "cookie":
        client.cookies.delete(CSRF_COOKIE)
    else:
        headers["X-CSRF-Token"] = "x" * 43
    assert client.patch(URL, headers=headers, json={"group_id": GROUP.id}).status_code == 403
    repository.save.assert_not_called()


@pytest.mark.parametrize(
    "method,path",
    [("get", URL), ("patch", URL), ("get", CATALOGUE), ("get", f"{CATALOGUE}/{GROUP.id}/context")],
)
def test_unauthenticated_requests(
    client: TestClient, application: FastAPI, method: str, path: str
) -> None:
    application.dependency_overrides.pop(get_current_session)
    response = client.request(
        method,
        path,
        headers=csrf_headers(client),
        json={"group_id": GROUP.id} if method == "patch" else None,
    )
    assert response.status_code == 401 and "Max-Age=0" in response.headers["set-cookie"]


@pytest.mark.parametrize("failure", ["canonical_user", "database", "commit", "upstream"])
def test_failures_never_return_success(
    client: TestClient, repository: Mock, users: Mock, provider: Mock, database: Mock, failure: str
) -> None:
    if failure == "canonical_user":
        users.lock_active.return_value = False
    elif failure == "database":
        repository.save.side_effect = SQLAlchemyError("private database details")
    elif failure == "commit":
        database.begin.return_value.__exit__.side_effect = SQLAlchemyError("private commit details")
    else:
        provider.list_groups.side_effect = AcademicProviderUnavailable("private upstream details")
    response = client.patch(URL, headers=csrf_headers(client), json={"group_id": GROUP.id})
    assert response.status_code == (401 if failure == "canonical_user" else 503)
    assert "private" not in response.text and response.headers["cache-control"] == "no-store"


def test_live_profile_lifecycle_and_auth_preservation(
    live_client: TestClient, concurrent_engine: Engine, password_hash: str, provider: Mock
) -> None:
    cast(FastAPI, live_client.app).state.academic_provider = provider
    seed_user(concurrent_engine, "student@example.com", password_hash)
    seed_user(concurrent_engine, "other@example.com", password_hash)
    browser_login(live_client)
    before = snapshot(concurrent_engine)
    assert live_client.get(URL).json() is None
    headers = csrf_headers(live_client)
    for patch, expected_group, expected_subgroup in [
        ({"group_id": GROUP.id, "subgroup": 1}, GROUP.id, 1),
        ({"group_id": GROUP.id}, GROUP.id, 1),
        ({"subgroup": None}, GROUP.id, None),
        ({"subgroup": 2}, GROUP.id, 2),
        ({"group_id": OTHER.id}, OTHER.id, None),
    ]:
        response = live_client.patch(URL, headers=headers, json=patch)
        assert response.status_code == 200, response.text
        assert (response.json()["group"]["id"], response.json()["subgroup"]) == (
            expected_group,
            expected_subgroup,
        )
        assert live_client.get(URL).json() == response.json()
    assert snapshot(concurrent_engine) == before
    browser_login(live_client, "other@example.com")
    assert live_client.get(URL).json() is None
    provider.list_groups.side_effect = AcademicProviderUnavailable()
    browser_login(live_client)
    assert live_client.get(URL).status_code == 200
    assert live_client.patch(URL, headers=headers, json={"subgroup": None}).status_code == 200
    assert live_client.patch(URL, headers=headers, json={"group_id": GROUP.id}).status_code == 503


def test_live_network_runs_outside_transactions_and_rechecks_user(
    live_client: TestClient, concurrent_engine: Engine, password_hash: str, provider: Mock
) -> None:
    cast(FastAPI, live_client.app).state.academic_provider = provider
    seed_user(concurrent_engine, "student@example.com", password_hash)
    browser_login(live_client)
    transactions: list[str] = []

    def begin(connection):
        transactions.append("begin")

    def commit(connection):
        transactions.append("commit")

    event.listen(concurrent_engine, "begin", begin)
    event.listen(concurrent_engine, "commit", commit)

    def groups():
        assert transactions[-1] == "commit"
        with Session(concurrent_engine) as writer, writer.begin():
            writer.execute(update(UserModel).values(status="disabled"))
        return [GROUP, OTHER]

    provider.list_groups.side_effect = groups
    try:
        response = live_client.patch(
            URL, headers=csrf_headers(live_client), json={"group_id": GROUP.id}
        )
        assert response.status_code == 401
        with Session(concurrent_engine) as database:
            assert database.scalar(select(AcademicProfileModel)) is None
    finally:
        event.remove(concurrent_engine, "begin", begin)
        event.remove(concurrent_engine, "commit", commit)


@pytest.mark.parametrize("failure", ["write", "commit"])
def test_live_http_rolls_back(
    live_client: TestClient,
    concurrent_engine: Engine,
    password_hash: str,
    provider: Mock,
    failure: str,
) -> None:
    cast(FastAPI, live_client.app).state.academic_provider = provider
    seed_user(concurrent_engine, "student@example.com", password_hash)
    browser_login(live_client)

    def fail_write(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO academic_profiles"):
            raise SQLAlchemyError("private write failure")

    def fail_commit(session: Session):
        if session.info.get("academic_write"):
            raise SQLAlchemyError("private commit failure")

    def mark_write(state):
        if state.is_insert and state.statement.table.name == "academic_profiles":
            state.session.info["academic_write"] = True

    if failure == "write":
        event.listen(concurrent_engine, "before_cursor_execute", fail_write)
    if failure == "commit":
        event.listen(Session, "do_orm_execute", mark_write)
        event.listen(Session, "before_commit", fail_commit)
    try:
        response = live_client.patch(
            URL, headers=csrf_headers(live_client), json={"group_id": GROUP.id}
        )
        assert response.status_code == 503 and "private" not in response.text
        with Session(concurrent_engine) as database:
            assert database.scalar(select(AcademicProfileModel)) is None
            assert database.scalar(select(UniversityGroupModel)) is None
    finally:
        if failure == "write":
            event.remove(concurrent_engine, "before_cursor_execute", fail_write)
        else:
            event.remove(Session, "do_orm_execute", mark_write)
            event.remove(Session, "before_commit", fail_commit)


@pytest.mark.parametrize("status", ["disabled", "missing"])
@pytest.mark.parametrize(
    "method,path",
    [
        ("get", URL),
        ("patch", URL),
        ("get", CATALOGUE),
        ("get", f"{CATALOGUE}/{GROUP.id}/context"),
    ],
)
def test_live_ineligible_users(
    live_client: TestClient,
    concurrent_engine: Engine,
    password_hash: str,
    provider: Mock,
    status: str,
    method: str,
    path: str,
) -> None:
    cast(FastAPI, live_client.app).state.academic_provider = provider
    seed_user(concurrent_engine, "student@example.com", password_hash)
    token = browser_login(live_client)
    headers = csrf_headers(live_client)
    with Session(concurrent_engine) as database, database.begin():
        if status == "missing":
            database.execute(delete(UserModel))
        else:
            database.execute(update(UserModel).values(status="disabled"))
    before = snapshot(concurrent_engine)
    response = live_client.request(
        method,
        path,
        headers=headers,
        json={"group_id": GROUP.id} if method == "patch" else None,
    )
    assert response.status_code == 401 and "Max-Age=0" in response.headers["set-cookie"]
    assert token not in response.text and snapshot(concurrent_engine) == before
    provider.list_groups.assert_not_called()


@pytest.mark.parametrize("path", [CATALOGUE, f"{CATALOGUE}/{GROUP.id}/context"])
def test_upstream_unavailable_reads_are_safe(client: TestClient, provider: Mock, path: str) -> None:
    provider.list_groups.side_effect = AcademicProviderUnavailable("private upstream failure")
    response = client.get(path)
    assert response.status_code == 503 and response.json() == {"detail": "Service unavailable."}
    assert response.headers["cache-control"] == "no-store"


def test_live_google_only_user_and_avatar_are_preserved(
    live_client: TestClient,
    concurrent_engine: Engine,
    provider: Mock,
) -> None:
    cast(FastAPI, live_client.app).state.academic_provider = provider
    token = generate_token()
    with Session(concurrent_engine) as database, database.begin():
        user = UserModel(email="google-only@example.com")
        database.add(user)
        database.flush()
        user.avatar_key = f"avatars/{user.id}/{uuid4().hex}.png"
        database.add(
            IdentityModel(user_id=user.id, provider="google", provider_subject=str(user.id))
        )
        database.add(
            SessionModel(
                user_id=user.id,
                token_hash=hash_token(token),
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
        )
    live_client.cookies.set(SESSION_COOKIE, token)
    before = snapshot(concurrent_engine)
    assert live_client.get(URL).json() is None
    response = live_client.patch(
        URL, headers=csrf_headers(live_client), json={"group_id": GROUP.id}
    )
    assert response.status_code == 200
    assert snapshot(concurrent_engine) == before
