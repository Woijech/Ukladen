from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, create_autospec
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_auth_http import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    browser_login,
    csrf_headers,
    seed_user,
)
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

from app.modules.auth.application.dto import IssuedSession
from app.modules.auth.domain.errors import InvalidSession
from app.modules.auth.infrastructure.orm import (
    CredentialModel,
    IdentityModel,
    OneTimeTokenModel,
    SessionModel,
)
from app.modules.auth.infrastructure.token_service import generate_token, hash_token
from app.modules.auth.presentation.dependencies import get_current_session
from app.modules.users.application.profile import ProfileService
from app.modules.users.domain.profile import ProfileUnavailable, UserProfile
from app.modules.users.infrastructure.orm import UserModel
from app.modules.users.infrastructure.repository import SqlAlchemyProfileRepository
from app.modules.users.presentation.routes import get_profiles

URL = "/api/v1/users/me"
FIELDS = {
    "avatar_url",
    "id",
    "email",
    "email_verified_at",
    "status",
    "display_name",
    "timezone",
    "locale",
    "created_at",
    "updated_at",
}


@pytest.fixture
def profiles(application: FastAPI, issued: IssuedSession) -> Mock:
    now = datetime.now(UTC)
    profile = UserProfile(
        issued.session.user_id, "student@example.com", None, "active", None, "UTC", "ru", now, now
    )
    service = create_autospec(ProfileService, instance=True)
    service.get.return_value = profile
    service.update.return_value = replace(profile, display_name="Alex")
    application.dependency_overrides[get_profiles] = lambda: service
    return service


def test_http_owner_safe_fields_and_openapi(
    client: TestClient, profiles: Mock, issued: IssuedSession
) -> None:
    response = client.get(URL)
    assert response.status_code == 200 and set(response.json()) == FIELDS
    assert response.headers["cache-control"] == "no-store"
    profiles.get.assert_called_once_with(issued.session.user_id)
    response = client.patch(URL, headers=csrf_headers(client), json={"display_name": " Alex "})
    assert response.status_code == 200 and set(response.json()) == FIELDS
    assert response.headers["cache-control"] == "no-store"
    profiles.update.assert_called_once_with(issued.session.user_id, {"display_name": "Alex"})
    schema = client.get("/api/openapi.json").json()
    assert set(schema["paths"][URL]) == {"get", "patch"}
    assert schema["components"]["schemas"]["ProfilePatch"]["additionalProperties"] is False


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"email": "secret"},
        {"timezone": None},
        {"locale": "fr"},
        {"display_name": " "},
        {"timezone": "secret-invalid-zone"},
    ],
)
def test_transport_errors_are_safe(
    client: TestClient, profiles: Mock, payload: dict[str, object]
) -> None:
    response = client.patch(URL, headers=csrf_headers(client), json=payload)
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request."}
    assert response.headers["cache-control"] == "no-store"
    profiles.update.assert_not_called()


@pytest.mark.parametrize(
    "failure", ["origin", "foreign_origin", "header", "cookie", "mismatch", "invalid"]
)
def test_patch_uses_existing_csrf(client: TestClient, profiles: Mock, failure: str) -> None:
    headers = csrf_headers(client)
    if failure == "origin":
        headers.pop("Origin")
    elif failure == "foreign_origin":
        headers["Origin"] = "https://attacker.example"
    elif failure == "header":
        headers.pop("X-CSRF-Token")
    elif failure == "cookie":
        client.cookies.delete(CSRF_COOKIE)
    else:
        headers["X-CSRF-Token"] = generate_token() if failure == "mismatch" else "bad"
    response = client.patch(URL, headers=headers, json={"locale": "en"})
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"
    profiles.update.assert_not_called()


@pytest.mark.parametrize("method", ["get", "patch"])
@pytest.mark.parametrize("failure", ["session", "canonical_user", "database", "commit"])
def test_failures_do_not_return_success(
    client: TestClient,
    application: FastAPI,
    profiles: Mock,
    database: Mock,
    method: str,
    failure: str,
) -> None:
    headers = csrf_headers(client)
    if failure == "session":

        def reject() -> None:
            raise InvalidSession("private-token")

        application.dependency_overrides[get_current_session] = reject
    elif failure == "canonical_user":
        profiles.get.side_effect = profiles.update.side_effect = ProfileUnavailable()
    elif failure == "database":
        profiles.get.side_effect = profiles.update.side_effect = SQLAlchemyError(
            "private-connection"
        )
    else:
        database.begin.return_value.__exit__.side_effect = SQLAlchemyError("private-connection")
    response = client.request(
        method, URL, headers=headers, json={"locale": "en"} if method == "patch" else None
    )
    assert response.status_code == (401 if failure in {"session", "canonical_user"} else 503)
    assert response.headers["cache-control"] == "no-store"
    assert "private" not in response.text


def snapshot(engine: Engine) -> dict[str, list[dict[str, object]]]:
    with engine.connect() as connection:
        return {
            model.__tablename__: [
                dict(row) for row in connection.execute(select(model.__table__)).mappings()
            ]
            for model in (
                UserModel,
                CredentialModel,
                IdentityModel,
                OneTimeTokenModel,
                SessionModel,
            )
        }


def test_live_google_only_profile_without_credentials(
    live_client: TestClient, concurrent_engine: Engine
) -> None:
    token = generate_token()
    with Session(concurrent_engine) as database, database.begin():
        user = UserModel(email="google-only@example.com", email_verified_at=datetime.now(UTC))
        database.add(user)
        database.flush()
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
    response = live_client.get(URL)
    assert response.status_code == 200
    profile = response.json()
    assert profile["email_verified_at"] is not None
    assert (profile["display_name"], profile["timezone"], profile["locale"]) == (None, "UTC", "ru")
    response = live_client.patch(URL, headers=csrf_headers(live_client), json={"locale": "en"})
    assert response.status_code == 200 and response.json()["locale"] == "en"
    after = snapshot(concurrent_engine)
    assert after["auth_credentials"] == []
    for table in ("auth_identities", "auth_sessions", "auth_one_time_tokens"):
        assert after[table] == before[table]


def test_live_profile_persistence_ownership_and_auth_preservation(
    live_client: TestClient, concurrent_engine: Engine, password_hash: str
) -> None:
    seed_user(concurrent_engine, "student@example.com", password_hash)
    seed_user(concurrent_engine, "other@example.com", password_hash)
    with Session(concurrent_engine) as database, database.begin():
        users = list(database.scalars(select(UserModel).order_by(UserModel.email)))
        for user in users:
            database.add(
                IdentityModel(user_id=user.id, provider="google", provider_subject=str(user.id))
            )
            for kind in ("email_verification", "password_reset"):
                database.add(
                    OneTimeTokenModel(
                        user_id=user.id,
                        token_type=kind,
                        token_hash=hash_token(generate_token()),
                        expires_at=datetime.now(UTC) + timedelta(hours=1),
                    )
                )
    token = browser_login(live_client)
    initial = snapshot(concurrent_engine)
    response = live_client.get(URL)
    assert response.status_code == 200 and set(response.json()) == FIELDS
    profile = response.json()
    assert (profile["display_name"], profile["timezone"], profile["locale"]) == (None, "UTC", "ru")
    assert profile["email_verified_at"] is None
    assert datetime.fromisoformat(profile["created_at"]).utcoffset() is not None
    assert snapshot(concurrent_engine) == initial
    headers = csrf_headers(live_client)
    for patch in (
        {"display_name": " Alex "},
        {"timezone": "Europe/Minsk"},
        {"locale": "en"},
        {"display_name": "Bob", "timezone": "Asia/Tokyo", "locale": "ru"},
        {"display_name": None},
    ):
        response = live_client.patch(URL, headers=headers, json=patch)
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        expected = profile | {
            key: value.strip() if isinstance(value, str) else value for key, value in patch.items()
        }
        current = response.json()
        assert current == expected | {"updated_at": current["updated_at"]}
        assert datetime.fromisoformat(current["updated_at"]) > datetime.fromisoformat(
            profile["updated_at"]
        )
        profile = current
        with Session(concurrent_engine) as database:
            stored = SqlAlchemyProfileRepository(database).get_active(UUID(profile["id"]))
            assert stored and stored.display_name == profile["display_name"]
            assert stored.timezone == profile["timezone"] and stored.locale == profile["locale"]
    after = snapshot(concurrent_engine)
    assert {k: v for k, v in initial.items() if k != "users"} == {
        k: v for k, v in after.items() if k != "users"
    }
    other_before = next(row for row in initial["users"] if row["email"] == "other@example.com")
    assert next(row for row in after["users"] if row["id"] == other_before["id"]) == other_before
    rejected = live_client.patch(
        URL, headers=headers, json={"id": str(other_before["id"]), "locale": "en"}
    )
    assert rejected.status_code == 422 and snapshot(concurrent_engine) == after
    assert live_client.cookies.get(SESSION_COOKIE) == token
    browser_login(live_client, "other@example.com")
    assert live_client.get(URL).json()["id"] == str(other_before["id"])
    assert live_client.get(URL).json()["timezone"] == "UTC"


@pytest.mark.parametrize("method", ["get", "patch"])
@pytest.mark.parametrize(
    "state", ["missing", "invalid", "unknown", "expired", "revoked", "disabled", "missing_user"]
)
def test_live_rejects_ineligible_sessions(
    live_client: TestClient, concurrent_engine: Engine, password_hash: str, method: str, state: str
) -> None:
    seed_user(concurrent_engine, "student@example.com", password_hash)
    token = browser_login(live_client)
    if state == "missing":
        live_client.cookies.delete(SESSION_COOKIE)
    elif state in {"invalid", "unknown"}:
        live_client.cookies.set(
            SESSION_COOKIE, "invalid" if state == "invalid" else generate_token()
        )
    elif state == "revoked":
        # Populate Redis first, then revoke through the canonical existing auth flow.
        assert live_client.get(URL).status_code == 200
        assert (
            live_client.post("/api/v1/auth/logout", headers=csrf_headers(live_client)).status_code
            == 204
        )
        live_client.cookies.set(SESSION_COOKIE, token)
    else:
        with Session(concurrent_engine) as database, database.begin():
            if state == "expired":
                now = datetime.now(UTC)
                database.execute(
                    update(SessionModel).values(
                        created_at=now - timedelta(days=2), expires_at=now - timedelta(days=1)
                    )
                )
            elif state == "disabled":
                assert live_client.get(URL).status_code == 200
                database.execute(update(UserModel).values(status="disabled"))
            else:
                user = database.scalar(select(UserModel))
                assert user
                database.delete(user)
    before = snapshot(concurrent_engine)
    response = live_client.request(
        method,
        URL,
        headers=csrf_headers(live_client),
        json={"locale": "en"} if method == "patch" else None,
    )
    assert response.status_code == 401 and response.headers["cache-control"] == "no-store"
    assert snapshot(concurrent_engine) == before


@pytest.mark.parametrize("failure", ["write", "commit"])
def test_live_write_and_commit_failure_roll_back(
    live_client: TestClient,
    concurrent_engine: Engine,
    password_hash: str,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    seed_user(concurrent_engine, "student@example.com", password_hash)
    token = browser_login(live_client)
    before = snapshot(concurrent_engine)
    original = SqlAlchemyProfileRepository.update_active

    def fail_write(
        self: SqlAlchemyProfileRepository, user_id: UUID, changes: dict[str, str | None]
    ) -> None:
        original(self, user_id, changes)
        raise SQLAlchemyError("private-write-details")

    def fail_commit(database: Session) -> None:
        if database.scalar(select(UserModel.display_name)) == "fail":
            raise SQLAlchemyError("private-commit-details")

    if failure == "write":
        monkeypatch.setattr(SqlAlchemyProfileRepository, "update_active", fail_write)
    else:
        event.listen(Session, "before_commit", fail_commit)
    try:
        response = live_client.patch(
            URL, headers=csrf_headers(live_client), json={"display_name": "fail", "locale": "en"}
        )
    finally:
        if failure == "commit":
            event.remove(Session, "before_commit", fail_commit)
    assert response.status_code == 503 and response.json() == {"detail": "Service unavailable."}
    assert response.headers["cache-control"] == "no-store"
    assert snapshot(concurrent_engine) == before
    assert live_client.cookies.get(SESSION_COOKIE) == token
