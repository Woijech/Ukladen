from typing import cast
from unittest.mock import Mock, create_autospec

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import Engine, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_auth_http import PASSWORD, SESSION_COOKIE, browser_login, csrf_headers, seed_user
from test_auth_http import application as application
from test_auth_http import browser_settings as browser_settings
from test_auth_http import client as client
from test_auth_http import concurrent_engine as concurrent_engine
from test_auth_http import database as database
from test_auth_http import issued as issued
from test_auth_http import limiter as limiter
from test_auth_http import live_client as live_client
from test_auth_http import login_service as login_service
from test_auth_http import password_hash as password_hash
from test_auth_http import sessions as sessions
from test_auth_http import settings as settings
from test_auth_password_recovery import NEW_PASSWORD

from app.core.config import Settings
from app.modules.auth.application.dto import IssuedSession
from app.modules.auth.application.password_recovery import PasswordRecoveryService
from app.modules.auth.application.ports import RateLimiterUnavailable, SessionCacheUnavailable
from app.modules.auth.domain.errors import InvalidCredentials, InvalidPassword, InvalidSession
from app.modules.auth.infrastructure.orm import CredentialModel, SessionModel
from app.modules.auth.infrastructure.request_protection import RedisRateLimiter
from app.modules.auth.infrastructure.token_service import hash_token
from app.modules.auth.presentation.dependencies import get_current_session, get_password_recovery
from app.modules.auth.presentation.schemas import PasswordChangeRequest
from app.modules.users.infrastructure.orm import UserModel

PATH = "/api/v1/auth/password/change"
PAYLOAD = {"current_password": PASSWORD, "new_password": NEW_PASSWORD}


@pytest.fixture
def password_service() -> Mock:
    return create_autospec(PasswordRecoveryService, instance=True)


@pytest.fixture
def password_client(client: TestClient, application: FastAPI, password_service: Mock) -> TestClient:
    application.dependency_overrides[get_password_recovery] = lambda: password_service
    return client


def test_change_http_keeps_cookie_and_passes_authenticated_owner(
    password_client: TestClient, password_service: Mock, issued: IssuedSession, limiter: Mock
) -> None:
    password_client.cookies.set(SESSION_COOKIE, issued.token)
    response = password_client.post(PATH, json=PAYLOAD, headers=csrf_headers(password_client))
    assert response.status_code == 204 and response.content == b""
    assert response.headers["cache-control"] == "no-store" and "set-cookie" not in response.headers
    assert password_client.cookies.get(SESSION_COOKIE) == issued.token
    password_service.change_password.assert_called_once_with(
        issued.session.user_id, issued.session.id, PASSWORD, NEW_PASSWORD
    )
    limiter.check.assert_called_once_with(f"password-change:{issued.session.user_id}", 5, 60)
    dto = PasswordChangeRequest.model_validate(PAYLOAD)
    assert PASSWORD not in repr(dto) and NEW_PASSWORD not in repr(dto)
    assert password_client.get("/api/openapi.json").json()["paths"][PATH]["post"]["responses"][
        "204"
    ]


@pytest.mark.parametrize("failure", ["credentials", "policy", "cache", "commit", "session"])
def test_change_errors_are_sanitized_and_never_report_success(
    password_client: TestClient, password_service: Mock, database: Mock, failure: str
) -> None:
    errors = {
        "credentials": InvalidCredentials("private details"),
        "policy": InvalidPassword("private details"),
        "cache": SessionCacheUnavailable("private details"),
        "session": InvalidSession("private details"),
    }
    if failure == "commit":
        database.begin.return_value.__exit__.side_effect = SQLAlchemyError("private details")
    else:
        password_service.change_password.side_effect = errors[failure]
    response = password_client.post(PATH, json=PAYLOAD, headers=csrf_headers(password_client))
    assert (
        response.status_code
        == {"credentials": 401, "policy": 400, "cache": 503, "commit": 503, "session": 401}[failure]
    )
    assert (
        "private" not in response.text
        and PASSWORD not in response.text
        and NEW_PASSWORD not in response.text
    )
    assert response.headers["cache-control"] == "no-store"
    assert ("set-cookie" in response.headers) == (failure == "session")
    if failure == "credentials":
        assert response.json() == {"detail": "Invalid current password."}
    elif failure == "policy":
        assert response.json() == {"detail": "New password does not meet the password policy."}


@pytest.mark.parametrize("missing", ["Origin", "X-CSRF-Token"])
def test_change_csrf_precedes_rate_limit_and_service(
    password_client: TestClient, password_service: Mock, limiter: Mock, missing: str
) -> None:
    headers = csrf_headers(password_client)
    headers.pop(missing)
    response = password_client.post(PATH, json=PAYLOAD, headers=headers)
    assert response.status_code == 403
    password_service.change_password.assert_not_called()
    limiter.check.assert_not_called()


def test_change_requires_authentication(
    password_client: TestClient, application: FastAPI, password_service: Mock, limiter: Mock
) -> None:
    application.dependency_overrides.pop(get_current_session)
    response = password_client.post(PATH, json=PAYLOAD, headers=csrf_headers(password_client))
    assert response.status_code == 401
    password_service.change_password.assert_not_called()
    limiter.check.assert_not_called()


@pytest.mark.parametrize("outage", [False, True])
def test_change_rate_rejection_precedes_password_service(
    password_client: TestClient, password_service: Mock, limiter: Mock, outage: bool
) -> None:
    if outage:
        limiter.check.side_effect = RateLimiterUnavailable("private details")
    else:
        limiter.check.return_value = (False, 17)
    response = password_client.post(PATH, json=PAYLOAD, headers=csrf_headers(password_client))
    assert response.status_code == (503 if outage else 429) and "private" not in response.text
    assert "set-cookie" not in response.headers and response.headers["cache-control"] == "no-store"
    if not outage:
        assert response.headers["retry-after"] == "17"
    password_service.change_password.assert_not_called()


@pytest.mark.parametrize("body", ["type", "extra", "json", "oversized", "missing"])
def test_change_validation_does_not_echo_passwords(
    password_client: TestClient, password_service: Mock, body: str
) -> None:
    headers = csrf_headers(password_client)
    if body == "json":
        response = password_client.post(
            PATH,
            headers=headers | {"Content-Type": "application/json"},
            content='{"new_password":"' + NEW_PASSWORD + '"',
        )
    else:
        values: dict[str, object] = dict(PAYLOAD)
        if body == "type":
            values["current_password"] = {"secret": PASSWORD}
        elif body == "extra":
            values["secret"] = NEW_PASSWORD
        elif body == "oversized":
            values["new_password"] = "x" * 1025
        else:
            values.pop("current_password")
        response = password_client.post(PATH, headers=headers, json=values)
    assert response.status_code == 422 and response.json() == {"detail": "Invalid request."}
    assert PASSWORD not in response.text and NEW_PASSWORD not in response.text
    password_service.change_password.assert_not_called()


@pytest.mark.parametrize(
    "field", ["auth_password_change_rate_limit", "auth_password_change_rate_window_seconds"]
)
def test_change_rate_settings_are_positive(browser_settings: Settings, field: str) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(browser_settings.model_dump() | {field: 0})


def test_live_http_change_and_per_user_rate_limit(
    live_client: TestClient, concurrent_engine: Engine, password_hash: str
) -> None:
    seed_user(concurrent_engine, "student@example.com", password_hash)
    seed_user(concurrent_engine, "other@example.com", password_hash)
    foreign = browser_login(live_client, "other@example.com")
    assert live_client.get("/api/v1/auth/sessions").status_code == 200
    first = browser_login(live_client)
    assert live_client.get("/api/v1/auth/sessions").status_code == 200
    current = browser_login(live_client)
    app = cast(FastAPI, live_client.app)
    redis: Redis = app.state.redis
    original_limiter = app.state.rate_limiter
    with Session(concurrent_engine) as database:
        current_row = database.scalar(
            select(SessionModel).where(SessionModel.token_hash == hash_token(current))
        )
        assert current_row
        user_id = current_row.user_id
    rate_key = f"ukladen:auth:rate:password-change:{user_id}"
    app.state.rate_limiter = RedisRateLimiter(redis)
    try:
        response = live_client.post(
            PATH,
            json=PAYLOAD | {"current_password": "wrong-password"},
            headers=csrf_headers(live_client),
        )
        assert response.status_code == 401 and "set-cookie" not in response.headers
        response = live_client.post(
            PATH, json=PAYLOAD | {"new_password": "short"}, headers=csrf_headers(live_client)
        )
        assert response.status_code == 400
        response = live_client.post(PATH, json=PAYLOAD, headers=csrf_headers(live_client))
        assert response.status_code == 204 and "set-cookie" not in response.headers
        assert live_client.cookies.get(SESSION_COOKIE) == current
        for token, revoked in ((first, True), (current, False), (foreign, False)):
            with Session(concurrent_engine) as database:
                row = database.scalar(
                    select(SessionModel).where(SessionModel.token_hash == hash_token(token))
                )
                assert row and (row.revoked_at is not None) == revoked
            assert bool(redis.exists(f"ukladen:auth:session:{hash_token(token)}")) != revoked
        live_client.cookies.set(SESSION_COOKIE, first, domain="testserver.local", path="/")
        assert live_client.get("/api/v1/auth/sessions").status_code == 401
        live_client.cookies.set(SESSION_COOKIE, current, domain="testserver.local", path="/")
        for _ in range(2):
            response = live_client.post(PATH, json=PAYLOAD, headers=csrf_headers(live_client))
            assert response.status_code == 401
        response = live_client.post(PATH, json=PAYLOAD, headers=csrf_headers(live_client))
        assert response.status_code == 429 and 0 < int(response.headers["retry-after"]) <= 60
        assert live_client.cookies.get(SESSION_COOKIE) == current
        # Rate keys depend on the account, not a spoofable address header.
        assert redis.get(rate_key) == b"6"
        app.state.rate_limiter = original_limiter
        response = live_client.post(
            "/api/v1/auth/login",
            json={"email": "student@example.com", "password": NEW_PASSWORD},
            headers=csrf_headers(live_client),
        )
        assert response.status_code == 200
        response = live_client.post(
            "/api/v1/auth/login",
            json={"email": "student@example.com", "password": PASSWORD},
            headers=csrf_headers(live_client),
        )
        assert response.status_code == 401
    finally:
        app.state.rate_limiter = original_limiter
        redis.delete(rate_key)


def test_live_http_change_cache_failure_and_disabled_account(
    live_client: TestClient,
    concurrent_engine: Engine,
    password_hash: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user(concurrent_engine, "student@example.com", password_hash)
    first = browser_login(live_client)
    current = browser_login(live_client)
    redis: Redis = cast(FastAPI, live_client.app).state.redis
    with monkeypatch.context() as patch:
        patch.setattr(redis, "delete", Mock(side_effect=RedisConnectionError("private details")))
        response = live_client.post(PATH, json=PAYLOAD, headers=csrf_headers(live_client))
    assert response.status_code == 503 and "private" not in response.text
    assert (
        "set-cookie" not in response.headers and live_client.cookies.get(SESSION_COOKIE) == current
    )
    with Session(concurrent_engine) as database:
        stored = database.scalar(select(CredentialModel))
        assert stored and stored.password_hash == password_hash
        assert all(row.revoked_at is None for row in database.scalars(select(SessionModel)))
    response = live_client.post(PATH, json=PAYLOAD, headers=csrf_headers(live_client))
    assert response.status_code == 204 and live_client.cookies.get(SESSION_COOKIE) == current
    live_client.cookies.set(SESSION_COOKIE, first, domain="testserver.local", path="/")
    assert live_client.get("/api/v1/auth/sessions").status_code == 401
    live_client.cookies.set(SESSION_COOKIE, current, domain="testserver.local", path="/")
    with Session(concurrent_engine) as database, database.begin():
        database.execute(update(UserModel).values(status="disabled"))
    response = live_client.post(PATH, json=PAYLOAD, headers=csrf_headers(live_client))
    assert response.status_code == 401 and live_client.cookies.get(SESSION_COOKIE) is None
