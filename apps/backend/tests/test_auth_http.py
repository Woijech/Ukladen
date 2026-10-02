import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from typing import cast
from unittest.mock import Mock, create_autospec
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import Engine, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_auth_login import PASSWORD
from test_auth_login import password_hash as password_hash
from test_auth_sessions import concurrent_engine as concurrent_engine
from test_auth_sessions import settings as settings

from app.core.config import Settings
from app.db.session import create_session_factory
from app.main import create_app
from app.modules.auth.application.dto import IssuedSession
from app.modules.auth.application.login import LoginService
from app.modules.auth.application.ports import (
    RateLimiter,
    RateLimiterUnavailable,
    SessionCacheUnavailable,
)
from app.modules.auth.application.service import SessionService
from app.modules.auth.domain.entities import AuthSession
from app.modules.auth.domain.errors import InvalidCredentials
from app.modules.auth.infrastructure.orm import CredentialModel, SessionModel
from app.modules.auth.infrastructure.request_protection import RedisRateLimiter
from app.modules.auth.infrastructure.token_service import generate_token, hash_token
from app.modules.auth.presentation.dependencies import (
    get_current_session,
    get_database,
    get_login,
    get_sessions,
)
from app.modules.users.infrastructure.orm import UserModel

ORIGIN = "https://testserver"
SESSION_COOKIE = "__Host-ukladen_session"
CSRF_COOKIE = "__Host-ukladen_csrf"


@pytest.fixture
def browser_settings(settings: Settings) -> Settings:
    return Settings.model_validate(
        settings.model_dump()
        | {
            "auth_session_cookie_name": SESSION_COOKIE,
            "auth_csrf_cookie_name": CSRF_COOKIE,
            "auth_cookie_secure": True,
            "auth_cookie_samesite": "lax",
            "auth_allowed_origins": [ORIGIN],
            "auth_login_rate_limit": 10,
            "auth_login_rate_window_seconds": 60,
        }
    )


@pytest.fixture
def issued() -> IssuedSession:
    token = generate_token()
    now = datetime.now(UTC)
    return IssuedSession(
        AuthSession(
            id=uuid4(),
            user_id=uuid4(),
            token_hash=hash_token(token),
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(days=30),
        ),
        token,
    )


@pytest.fixture
def database() -> Mock:
    return create_autospec(Session, instance=True)


@pytest.fixture
def login_service(issued: IssuedSession) -> Mock:
    service = create_autospec(LoginService, instance=True)
    service.login.return_value = issued
    return service


@pytest.fixture
def sessions(issued: IssuedSession) -> Mock:
    service = create_autospec(SessionService, instance=True)
    service.validate.return_value = issued.session
    return service


@pytest.fixture
def limiter() -> Mock:
    limiter = create_autospec(RateLimiter, instance=True)
    limiter.check.return_value = (True, 60)
    return limiter


@pytest.fixture
def application(
    browser_settings: Settings,
    database: Mock,
    login_service: Mock,
    sessions: Mock,
    issued: IssuedSession,
) -> FastAPI:
    application = create_app(browser_settings)
    application.dependency_overrides[get_database] = lambda: database
    application.dependency_overrides[get_login] = lambda: login_service
    application.dependency_overrides[get_sessions] = lambda: sessions
    application.dependency_overrides[get_current_session] = lambda: issued.session
    return application


@pytest.fixture
def client(application: FastAPI, limiter: Mock) -> Iterator[TestClient]:
    with TestClient(application, base_url=ORIGIN, client=("192.0.2.10", 50000)) as client:
        application.state.rate_limiter = limiter
        yield client


def csrf_headers(client: TestClient) -> dict[str, str]:
    response = client.get("/api/v1/auth/csrf")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}


def test_cookie_flags_and_login_response(
    client: TestClient, issued: IssuedSession, login_service: Mock, browser_settings: Settings
) -> None:
    headers = csrf_headers(client)
    again = client.get("/api/v1/auth/csrf")
    assert again.json()["csrf_token"] == headers["X-CSRF-Token"]
    response = client.post(
        "/api/v1/auth/login",
        headers=headers,
        json={"email": "student@example.com", "password": PASSWORD},
    )
    assert response.status_code == 200
    assert response.json()["user_id"] == str(issued.session.user_id)
    assert response.json()["session_id"] == str(issued.session.id)
    assert issued.token not in response.text and PASSWORD not in response.text
    assert response.headers["cache-control"] == "no-store"
    for name, result in ((SESSION_COOKIE, response), (CSRF_COOKIE, again)):
        parsed = SimpleCookie()
        parsed.load(result.headers["set-cookie"])
        cookie = parsed[name]
        assert cookie["httponly"] and cookie["secure"]
        assert cookie["samesite"] == "lax" and cookie["path"] == "/" and not cookie["domain"]
        assert int(cookie["max-age"]) == browser_settings.auth_session_ttl_seconds
    assert client.cookies.get(SESSION_COOKIE) == issued.token
    assert login_service.login.call_args.args == ("student@example.com", PASSWORD)
    assert str(login_service.login.call_args.kwargs["ip_address"]) == "192.0.2.10"
    assert client.get("/api/openapi.json").json()["paths"]["/api/v1/auth/login"]["post"]


@pytest.mark.parametrize(
    "failure", ["origin", "cross_origin", "header", "cookie", "mismatch", "malformed", "oversized"]
)
def test_csrf_rejects_before_login(
    client: TestClient, login_service: Mock, limiter: Mock, failure: str
) -> None:
    headers = csrf_headers(client)
    if failure == "origin":
        headers.pop("Origin")
    elif failure == "cross_origin":
        headers["Origin"] = "https://attacker.example"
    elif failure == "header":
        headers.pop("X-CSRF-Token")
    elif failure == "cookie":
        client.cookies.clear()
    elif failure == "mismatch":
        headers["X-CSRF-Token"] = generate_token()
    elif failure == "malformed":
        headers["X-CSRF-Token"] = "!" * 43
    else:
        headers["X-CSRF-Token"] = "x" * 44
    response = client.post(
        "/api/v1/auth/login",
        headers=headers,
        json={"email": "student@example.com", "password": PASSWORD},
    )
    assert response.status_code == 403
    login_service.login.assert_not_called()
    limiter.check.assert_not_called()


def test_cross_site_bootstrap_is_rejected(client: TestClient) -> None:
    response = client.get("/api/v1/auth/csrf", headers={"Sec-Fetch-Site": "cross-site"})
    assert response.status_code == 403 and "set-cookie" not in response.headers


@pytest.mark.parametrize("outage", [False, True])
def test_login_rate_limiting(
    client: TestClient, limiter: Mock, login_service: Mock, outage: bool
) -> None:
    headers = csrf_headers(client) | {"X-Forwarded-For": "203.0.113.99"}
    if outage:
        limiter.check.side_effect = RateLimiterUnavailable("private connection details")
    else:
        limiter.check.return_value = (False, 23)
    response = client.post(
        "/api/v1/auth/login",
        headers=headers,
        json={"email": "student@example.com", "password": PASSWORD},
    )
    assert response.status_code == (503 if outage else 429)
    assert "private" not in response.text and "set-cookie" not in response.headers
    if not outage:
        assert response.headers["retry-after"] == "23"
    limiter.check.assert_called_once_with(f"login:{hash_token('192.0.2.10')}", 10, 60)
    login_service.login.assert_not_called()


@pytest.mark.parametrize("failure", ["credentials", "commit"])
def test_login_failures_never_issue_cookie(
    client: TestClient, login_service: Mock, database: Mock, failure: str
) -> None:
    headers = csrf_headers(client)
    if failure == "credentials":
        login_service.login.side_effect = InvalidCredentials("private details")
    else:
        database.begin.return_value.__exit__.side_effect = SQLAlchemyError("private details")
    response = client.post(
        "/api/v1/auth/login",
        headers=headers,
        json={"email": "student@example.com", "password": PASSWORD},
    )
    assert response.status_code == (401 if failure == "credentials" else 503)
    assert "private" not in response.text and "set-cookie" not in response.headers


@pytest.mark.parametrize("body", ["type", "extra", "json"])
def test_validation_errors_do_not_echo_secrets(
    client: TestClient, login_service: Mock, body: str
) -> None:
    secret = "synthetic-sensitive-request-value"
    headers = csrf_headers(client)
    if body == "type":
        response = client.post(
            "/api/v1/auth/login",
            headers=headers,
            json={"email": "student@example.com", "password": {"secret": secret}},
        )
    elif body == "extra":
        response = client.post(
            "/api/v1/auth/login",
            headers=headers,
            json={"email": "student@example.com", "password": PASSWORD, "token": secret},
        )
    else:
        response = client.post(
            "/api/v1/auth/login",
            headers=headers | {"Content-Type": "application/json"},
            content='{"password":"' + secret + '"',
        )
    assert response.status_code == 422 and response.json() == {"detail": "Invalid request."}
    assert secret not in response.text and PASSWORD not in response.text
    login_service.login.assert_not_called()


@pytest.mark.parametrize("path", ["logout", "logout-all"])
@pytest.mark.parametrize("outage", [False, True])
def test_logout_cookie_clearing_follows_revocation(
    client: TestClient, sessions: Mock, issued: IssuedSession, path: str, outage: bool
) -> None:
    headers = csrf_headers(client)
    method = sessions.revoke if path == "logout" else sessions.revoke_all_for_user
    if outage:
        method.side_effect = SessionCacheUnavailable("private details")
    response = client.post(f"/api/v1/auth/{path}", headers=headers)
    method.assert_called_once_with(
        issued.session.id if path == "logout" else issued.session.user_id
    )
    assert response.status_code == (503 if outage else 204)
    if outage:
        assert "set-cookie" not in response.headers and "private" not in response.text
    else:
        assert not response.content
        parsed = SimpleCookie()
        parsed.load(response.headers["set-cookie"])
        assert parsed[SESSION_COOKIE]["max-age"] == "0"
        assert parsed[SESSION_COOKIE]["secure"] and parsed[SESSION_COOKIE]["httponly"]


@pytest.mark.parametrize("active", [False, True])
def test_authenticated_dependency_checks_active_user(
    client: TestClient,
    application: FastAPI,
    database: Mock,
    sessions: Mock,
    issued: IssuedSession,
    active: bool,
) -> None:
    application.dependency_overrides.pop(get_current_session)
    headers = csrf_headers(client)
    client.cookies.set(SESSION_COOKIE, issued.token)
    database.scalar.return_value = issued.session.user_id if active else None
    response = client.post("/api/v1/auth/logout", headers=headers)
    assert response.status_code == (204 if active else 401)
    assert database.begin.call_count == (2 if active else 1)
    if not active:
        sessions.revoke.assert_not_called()
        assert "Max-Age=0" in response.headers["set-cookie"]


def test_browser_settings_reject_unsafe_or_ambiguous_configuration(
    browser_settings: Settings,
) -> None:
    for update_values in (
        {"auth_cookie_secure": False},
        {"auth_csrf_cookie_name": SESSION_COOKIE},
        {"auth_session_cookie_name": "invalid;cookie"},
        {"auth_cookie_samesite": "none"},
        {"auth_allowed_origins": [ORIGIN + "/path"]},
        {"auth_allowed_origins": ["https://user:private@testserver"]},
        {"auth_login_rate_limit": 0},
        {"auth_login_rate_window_seconds": 0},
    ):
        with pytest.raises(ValidationError) as error:
            Settings.model_validate(browser_settings.model_dump() | update_values)
        assert "private" not in str(error.value)
    local = Settings.model_validate(
        browser_settings.model_dump()
        | {
            "auth_cookie_secure": False,
            "auth_session_cookie_name": "ukladen_session",
            "auth_csrf_cookie_name": "ukladen_csrf",
            "auth_allowed_origins": ["http://localhost:8080"],
        }
    )
    assert not local.auth_cookie_secure


@pytest.mark.parametrize("result", [None, [], [1, "60"], [0, 60], [1, -1]])
def test_rate_limiter_rejects_invalid_redis_responses(result: object) -> None:
    redis = create_autospec(Redis, instance=True)
    redis.eval.return_value = result
    with pytest.raises(RateLimiterUnavailable):
        RedisRateLimiter(redis).check("test", 10, 60)


def test_rate_limiter_sanitizes_redis_errors() -> None:
    redis = create_autospec(Redis, instance=True)
    redis.eval.side_effect = RedisConnectionError("private connection details")
    with pytest.raises(RateLimiterUnavailable) as error:
        RedisRateLimiter(redis).check("test", 10, 60)
    assert "private" not in str(error.value) and error.value.__suppress_context__


def test_live_redis_rate_window() -> None:
    url = os.environ.get("AUTH_TEST_REDIS_URL")
    if not url:
        pytest.skip("Set AUTH_TEST_REDIS_URL to run rate-limit integration checks.")
    redis = Redis.from_url(url, socket_connect_timeout=3, socket_timeout=3)
    key = f"test:{uuid4().hex}"
    storage_key = f"ukladen:auth:rate:{key}"
    limiter = RedisRateLimiter(redis)
    try:
        assert limiter.check(key, 2, 60)[0]
        assert limiter.check(key, 2, 60)[0]
        allowed, retry = limiter.check(key, 2, 60)
        assert not allowed and 0 < retry <= 60
        ttl = redis.ttl(storage_key)
        assert isinstance(ttl, int) and 0 < ttl <= 60
        redis.delete(storage_key)
        assert limiter.check(key, 2, 60)[0]
    finally:
        redis.delete(storage_key)
        redis.close()


@pytest.fixture
def live_client(concurrent_engine: Engine, browser_settings: Settings) -> Iterator[TestClient]:
    url = os.environ.get("AUTH_TEST_REDIS_URL")
    if not url:
        pytest.skip("Set AUTH_TEST_REDIS_URL to run HTTP integration checks.")
    redis = Redis.from_url(url, socket_connect_timeout=3, socket_timeout=3)
    application = create_app(browser_settings)
    try:
        with TestClient(application, base_url=ORIGIN, client=("192.0.2.10", 50000)) as client:
            application.state.session_factory = create_session_factory(concurrent_engine)
            application.state.redis = redis
            limiter = create_autospec(RateLimiter, instance=True)
            limiter.check.return_value = (True, 60)
            application.state.rate_limiter = limiter
            yield client
    finally:
        with Session(concurrent_engine) as database:
            keys = [
                f"ukladen:auth:session:{token_hash}"
                for token_hash in database.scalars(select(SessionModel.token_hash))
            ]
        if keys:
            redis.delete(*keys)
        redis.close()


def seed_user(engine: Engine, email: str, password_hash: str) -> None:
    with Session(engine) as database, database.begin():
        user = UserModel(email=email)
        database.add(user)
        database.flush()
        database.add(CredentialModel(user_id=user.id, password_hash=password_hash))


def browser_login(client: TestClient, email: str = "student@example.com") -> str:
    response = client.post(
        "/api/v1/auth/login",
        headers=csrf_headers(client),
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200
    token = client.cookies.get(SESSION_COOKIE)
    assert token and token not in response.text
    return token


def test_live_http_login_logout_all(
    live_client: TestClient, concurrent_engine: Engine, password_hash: str
) -> None:
    seed_user(concurrent_engine, "student@example.com", password_hash)
    seed_user(concurrent_engine, "other@example.com", password_hash)
    other_token = browser_login(live_client, "other@example.com")
    first = browser_login(live_client)
    second = browser_login(live_client)
    with Session(concurrent_engine) as database:
        stored = database.scalar(
            select(SessionModel).where(SessionModel.token_hash == hash_token(second))
        )
        assert stored and stored.revoked_at is None and str(stored.ip_address) == "192.0.2.10"
    response = live_client.post("/api/v1/auth/logout", headers=csrf_headers(live_client))
    assert response.status_code == 204 and live_client.cookies.get(SESSION_COOKIE) is None
    live_client.cookies.set(SESSION_COOKIE, first, domain="testserver.local", path="/")
    assert (
        live_client.post("/api/v1/auth/logout-all", headers=csrf_headers(live_client)).status_code
        == 204
    )
    assert live_client.cookies.get(SESSION_COOKIE) is None
    with Session(concurrent_engine) as database:
        for token in (first, second):
            stored = database.scalar(
                select(SessionModel).where(SessionModel.token_hash == hash_token(token))
            )
            assert stored and stored.revoked_at is not None
        stored = database.scalar(
            select(SessionModel).where(SessionModel.token_hash == hash_token(other_token))
        )
        assert stored and stored.revoked_at is None
    live_client.cookies.set(SESSION_COOKIE, first, domain="testserver.local", path="/")
    assert (
        live_client.post("/api/v1/auth/logout", headers=csrf_headers(live_client)).status_code
        == 401
    )


def test_live_http_disabled_account_and_redis_outage(
    live_client: TestClient,
    concurrent_engine: Engine,
    password_hash: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user(concurrent_engine, "student@example.com", password_hash)
    token = browser_login(live_client)
    client_redis: Redis = cast(FastAPI, live_client.app).state.redis
    with Session(concurrent_engine) as database, database.begin():
        database.execute(update(UserModel).values(status="disabled"))
    response = live_client.post("/api/v1/auth/logout", headers=csrf_headers(live_client))
    assert response.status_code == 401 and live_client.cookies.get(SESSION_COOKIE) is None
    with Session(concurrent_engine) as database, database.begin():
        database.execute(update(UserModel).values(status="active"))
    live_client.cookies.set(SESSION_COOKIE, token, domain="testserver.local", path="/")
    with monkeypatch.context() as patch:
        patch.setattr(
            client_redis, "get", Mock(side_effect=RedisConnectionError("private details"))
        )
        patch.setattr(
            client_redis, "set", Mock(side_effect=RedisConnectionError("private details"))
        )
        patch.setattr(
            client_redis, "delete", Mock(side_effect=RedisConnectionError("private details"))
        )
        response = live_client.post("/api/v1/auth/logout", headers=csrf_headers(live_client))
    assert response.status_code == 503 and "private" not in response.text
    assert "set-cookie" not in response.headers and live_client.cookies.get(SESSION_COOKIE) == token
    with Session(concurrent_engine) as database:
        stored = database.scalar(
            select(SessionModel).where(SessionModel.token_hash == hash_token(token))
        )
        assert stored and stored.revoked_at is None
    assert (
        live_client.post("/api/v1/auth/logout", headers=csrf_headers(live_client)).status_code
        == 204
    )
