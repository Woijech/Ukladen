from datetime import UTC, datetime, timedelta
from ipaddress import IPv6Address
from typing import cast
from unittest.mock import Mock, create_autospec
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import Engine, delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_auth_http import ORIGIN, PASSWORD, SESSION_COOKIE, browser_login, csrf_headers, seed_user
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
from app.modules.auth.domain.entities import TokenType
from app.modules.auth.domain.errors import InvalidOneTimeToken, InvalidPassword
from app.modules.auth.infrastructure.orm import CredentialModel, OneTimeTokenModel, SessionModel
from app.modules.auth.infrastructure.request_protection import RedisRateLimiter
from app.modules.auth.infrastructure.token_service import generate_token, hash_token
from app.modules.auth.presentation.dependencies import get_current_session, get_password_recovery
from app.modules.auth.presentation.schemas import PasswordResetConfirmationRequest
from app.modules.users.infrastructure.orm import UserModel

PATH = "/api/v1/auth/password-reset/confirm"
TOKEN = "a" * 43
PAYLOAD = {"token": TOKEN, "new_password": NEW_PASSWORD}


@pytest.fixture
def reset_service() -> Mock:
    return create_autospec(PasswordRecoveryService, instance=True)


@pytest.fixture
def reset_client(client: TestClient, application: FastAPI, reset_service: Mock) -> TestClient:
    application.dependency_overrides[get_password_recovery] = lambda: reset_service
    application.dependency_overrides.pop(get_current_session)
    return client


def test_reset_needs_no_login_and_clears_cookie_after_success(
    reset_client: TestClient,
    reset_service: Mock,
    sessions: Mock,
    limiter: Mock,
    issued: IssuedSession,
) -> None:
    headers = csrf_headers(reset_client) | {"X-Forwarded-For": "203.0.113.99"}
    for session_token in (None, issued.token):
        if session_token:
            reset_client.cookies.set(
                SESSION_COOKIE, session_token, domain="testserver.local", path="/"
            )
        response = reset_client.post(PATH, json=PAYLOAD, headers=headers)
        assert response.status_code == 204 and response.content == b""
        assert response.headers["cache-control"] == "no-store"
        assert "Max-Age=0" in response.headers["set-cookie"]
        assert reset_client.cookies.get(SESSION_COOKIE) is None
    reset_service.confirm_reset.assert_called_with(TOKEN, NEW_PASSWORD)
    assert reset_service.confirm_reset.call_count == 2
    sessions.validate.assert_not_called()
    limiter.check.assert_called_with(f"password-reset-confirm:{hash_token('192.0.2.10')}", 5, 60)
    payload = PasswordResetConfirmationRequest.model_validate(PAYLOAD)
    for secret in (TOKEN, NEW_PASSWORD):
        assert secret not in repr(payload) and secret not in payload.model_dump_json()
        assert secret not in response.text
    assert "204" in reset_client.get("/api/openapi.json").json()["paths"][PATH]["post"]["responses"]


@pytest.mark.parametrize("failure", ["token", "policy", "cache", "database", "commit"])
def test_reset_errors_never_clear_cookie_or_echo_secrets(
    reset_client: TestClient,
    reset_service: Mock,
    database: Mock,
    issued: IssuedSession,
    failure: str,
) -> None:
    private = TOKEN + NEW_PASSWORD
    errors = {
        "token": InvalidOneTimeToken(private),
        "policy": InvalidPassword(private),
        "cache": SessionCacheUnavailable(private),
        "database": SQLAlchemyError(private),
    }
    if failure == "commit":
        database.begin.return_value.__exit__.side_effect = SQLAlchemyError(private)
    else:
        reset_service.confirm_reset.side_effect = errors[failure]
    reset_client.cookies.set(SESSION_COOKIE, issued.token)
    response = reset_client.post(PATH, json=PAYLOAD, headers=csrf_headers(reset_client))
    assert response.status_code == (400 if failure in ("token", "policy") else 503)
    expected = {
        "token": "Invalid or expired token.",
        "policy": "New password does not meet the password policy.",
    }.get(failure, "Service unavailable.")
    assert response.json() == {"detail": expected}
    assert TOKEN not in response.text and NEW_PASSWORD not in response.text
    assert "set-cookie" not in response.headers
    assert response.headers["cache-control"] == "no-store"
    assert reset_client.cookies.get(SESSION_COOKIE) == issued.token


@pytest.mark.parametrize("missing", ["Origin", "X-CSRF-Token"])
def test_reset_csrf_precedes_rate_limit_and_service(
    reset_client: TestClient, reset_service: Mock, limiter: Mock, missing: str
) -> None:
    headers = csrf_headers(reset_client)
    headers.pop(missing)
    response = reset_client.post(PATH, json=PAYLOAD, headers=headers)
    assert response.status_code == 403 and "set-cookie" not in response.headers
    limiter.check.assert_not_called()
    reset_service.confirm_reset.assert_not_called()


@pytest.mark.parametrize("outage", [False, True])
def test_reset_rate_rejection_precedes_service(
    reset_client: TestClient, reset_service: Mock, limiter: Mock, outage: bool
) -> None:
    if outage:
        limiter.check.side_effect = RateLimiterUnavailable(TOKEN + NEW_PASSWORD)
    else:
        limiter.check.return_value = (False, 17)
    response = reset_client.post(PATH, json=PAYLOAD, headers=csrf_headers(reset_client))
    assert response.status_code == (503 if outage else 429)
    assert TOKEN not in response.text and NEW_PASSWORD not in response.text
    assert "set-cookie" not in response.headers and response.headers["cache-control"] == "no-store"
    if not outage:
        assert response.headers["retry-after"] == "17"
    reset_service.confirm_reset.assert_not_called()


@pytest.mark.parametrize(
    "body",
    ["token_type", "password_type", "missing", "extra", "short", "long", "password_long", "json"],
)
def test_reset_request_validation_never_echoes_secrets(
    reset_client: TestClient, reset_service: Mock, body: str
) -> None:
    headers = csrf_headers(reset_client)
    if body == "json":
        response = reset_client.post(
            PATH,
            content='{"token":"' + TOKEN,
            headers=headers | {"Content-Type": "application/json"},
        )
    else:
        payload = {
            "token_type": PAYLOAD | {"token": {"secret": TOKEN}},
            "password_type": PAYLOAD | {"new_password": {"secret": NEW_PASSWORD}},
            "missing": {"token": TOKEN},
            "extra": PAYLOAD | {"extra": TOKEN + NEW_PASSWORD},
            "short": PAYLOAD | {"token": TOKEN[:-1]},
            "long": PAYLOAD | {"token": TOKEN + "a"},
            "password_long": PAYLOAD | {"new_password": "x" * 1025},
        }[body]
        response = reset_client.post(PATH, json=payload, headers=headers)
    assert response.status_code == 422 and response.json() == {"detail": "Invalid request."}
    assert TOKEN not in response.text and NEW_PASSWORD not in response.text
    assert "set-cookie" not in response.headers and response.headers["cache-control"] == "no-store"
    reset_service.confirm_reset.assert_not_called()


@pytest.mark.parametrize(
    "field",
    ["auth_password_reset_confirm_rate_limit", "auth_password_reset_confirm_rate_window_seconds"],
)
def test_reset_rate_settings_are_positive(browser_settings: Settings, field: str) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(browser_settings.model_dump() | {field: 0})


def seed_reset_token(engine: Engine) -> tuple[UUID, UUID, str]:
    with Session(engine) as database, database.begin():
        user_id = database.scalar(
            select(UserModel.id).where(UserModel.email == "student@example.com")
        )
        assert user_id
        raw_token = generate_token()
        now = datetime.now(UTC)
        token = OneTimeTokenModel(
            user_id=user_id,
            token_type=TokenType.PASSWORD_RESET,
            token_hash=hash_token(raw_token),
            created_at=now - timedelta(hours=1),
            expires_at=now + timedelta(hours=1),
        )
        database.add(token)
        database.flush()
        return user_id, token.id, raw_token


def test_live_reset_revokes_owned_sessions_and_allows_new_password_login(
    live_client: TestClient, concurrent_engine: Engine, password_hash: str
) -> None:
    seed_user(concurrent_engine, "student@example.com", password_hash)
    seed_user(concurrent_engine, "other@example.com", password_hash)
    foreign = browser_login(live_client, "other@example.com")
    assert live_client.get("/api/v1/auth/sessions").status_code == 200
    first = browser_login(live_client)
    assert live_client.get("/api/v1/auth/sessions").status_code == 200
    current = browser_login(live_client)
    assert live_client.get("/api/v1/auth/sessions").status_code == 200
    user_id, token_id, raw_token = seed_reset_token(concurrent_engine)
    redis: Redis = cast(FastAPI, live_client.app).state.redis
    headers = csrf_headers(live_client)
    payload = PAYLOAD | {"token": raw_token}
    response = live_client.post(PATH, json=payload, headers=headers)
    assert response.status_code == 204 and live_client.cookies.get(SESSION_COOKIE) is None
    assert response.headers["cache-control"] == "no-store"
    with Session(concurrent_engine) as database:
        token = database.get(OneTimeTokenModel, token_id)
        credential = database.get(CredentialModel, user_id)
        user = database.get(UserModel, user_id)
        assert token and token.used_at
        assert credential and credential.password_updated_at == token.used_at
        assert credential.password_hash != password_hash
        assert user and user.email_verified_at is None and user.status == "active"
        for session in database.scalars(select(SessionModel)):
            assert (session.revoked_at is not None) == (session.user_id == user_id)
    for session_token in (first, current):
        assert not redis.exists(f"ukladen:auth:session:{hash_token(session_token)}")
        live_client.cookies.set(SESSION_COOKIE, session_token, domain="testserver.local", path="/")
        assert live_client.get("/api/v1/auth/sessions").status_code == 401
    assert redis.exists(f"ukladen:auth:session:{hash_token(foreign)}")
    live_client.cookies.set(SESSION_COOKIE, foreign, domain="testserver.local", path="/")
    assert live_client.get("/api/v1/auth/sessions").status_code == 200
    replay = live_client.post(PATH, json=payload, headers=headers)
    assert replay.status_code == 400 and "set-cookie" not in replay.headers
    assert live_client.cookies.get(SESSION_COOKIE) == foreign
    for password, expected in ((PASSWORD, 401), (NEW_PASSWORD, 200)):
        response = live_client.post(
            "/api/v1/auth/login",
            json={"email": "student@example.com", "password": password},
            headers=headers,
        )
        assert response.status_code == expected


@pytest.mark.parametrize(
    "state",
    [
        "unknown",
        "malformed",
        "expired",
        "future",
        "used",
        "wrong_type",
        "disabled",
        "no_credential",
        "policy",
    ],
)
def test_live_reset_rejection_preserves_token_password_and_sessions(
    live_client: TestClient, concurrent_engine: Engine, password_hash: str, state: str
) -> None:
    seed_user(concurrent_engine, "student@example.com", password_hash)
    session_token = browser_login(live_client)
    user_id, token_id, raw_token = seed_reset_token(concurrent_engine)
    used_at = None
    with Session(concurrent_engine) as database, database.begin():
        token = database.get(OneTimeTokenModel, token_id)
        user = database.get(UserModel, user_id)
        assert token and user
        if state == "unknown":
            raw_token = generate_token()
        elif state == "malformed":
            raw_token = "!" * 43
        elif state == "expired":
            token.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        elif state == "future":
            token.created_at = datetime.now(UTC) + timedelta(minutes=1)
        elif state == "used":
            used_at = token.used_at = datetime.now(UTC) - timedelta(minutes=1)
        elif state == "wrong_type":
            token.token_type = TokenType.EMAIL_VERIFICATION
        elif state == "disabled":
            user.status = "disabled"
        elif state == "no_credential":
            database.execute(delete(CredentialModel).where(CredentialModel.user_id == user_id))
    payload = PAYLOAD | {"token": raw_token}
    if state == "policy":
        payload["new_password"] = "short"
    response = live_client.post(PATH, json=payload, headers=csrf_headers(live_client))
    assert response.status_code == 400
    assert response.json() == {
        "detail": "New password does not meet the password policy."
        if state == "policy"
        else "Invalid or expired token."
    }
    assert raw_token not in response.text and NEW_PASSWORD not in response.text
    assert (
        "set-cookie" not in response.headers
        and live_client.cookies.get(SESSION_COOKIE) == session_token
    )
    with Session(concurrent_engine) as database:
        token = database.get(OneTimeTokenModel, token_id)
        credential = database.get(CredentialModel, user_id)
        session = database.scalar(select(SessionModel))
        assert token and token.used_at == used_at
        assert session and session.revoked_at is None
        if state == "no_credential":
            assert credential is None
        else:
            assert credential and credential.password_hash == password_hash


def test_live_reset_cache_failure_rolls_back_and_can_retry_without_login(
    live_client: TestClient,
    concurrent_engine: Engine,
    password_hash: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user(concurrent_engine, "student@example.com", password_hash)
    session_token = browser_login(live_client)
    assert live_client.get("/api/v1/auth/sessions").status_code == 200
    user_id, token_id, raw_token = seed_reset_token(concurrent_engine)
    redis: Redis = cast(FastAPI, live_client.app).state.redis
    payload = PAYLOAD | {"token": raw_token}
    headers = csrf_headers(live_client)
    with monkeypatch.context() as patch:
        patch.setattr(
            redis, "delete", Mock(side_effect=RedisConnectionError(raw_token + NEW_PASSWORD))
        )
        response = live_client.post(PATH, json=payload, headers=headers)
    assert response.status_code == 503 and response.json() == {"detail": "Service unavailable."}
    assert raw_token not in response.text and NEW_PASSWORD not in response.text
    assert (
        "set-cookie" not in response.headers
        and live_client.cookies.get(SESSION_COOKIE) == session_token
    )
    with Session(concurrent_engine) as database:
        token = database.get(OneTimeTokenModel, token_id)
        credential = database.get(CredentialModel, user_id)
        session = database.scalar(select(SessionModel))
        assert token and token.used_at is None
        assert credential and credential.password_hash == password_hash
        assert session and session.revoked_at is None
    assert redis.exists(f"ukladen:auth:session:{hash_token(session_token)}")
    live_client.cookies.delete(SESSION_COOKIE)
    response = live_client.post(PATH, json=payload, headers=headers)
    assert response.status_code == 204
    with Session(concurrent_engine) as database:
        token = database.get(OneTimeTokenModel, token_id)
        credential = database.get(CredentialModel, user_id)
        session = database.scalar(select(SessionModel))
        assert token and token.used_at
        assert credential and credential.password_hash != password_hash
        assert session and session.revoked_at
    assert not redis.exists(f"ukladen:auth:session:{hash_token(session_token)}")


def test_live_reset_native_rate_window(live_client: TestClient) -> None:
    app = cast(FastAPI, live_client.app)
    redis: Redis = app.state.redis
    original_limiter = app.state.rate_limiter
    original_settings = app.state.settings
    peer = str(IPv6Address(uuid4().int))
    rate_key = f"ukladen:auth:rate:password-reset-confirm:{hash_token(peer)}"
    app.state.rate_limiter = RedisRateLimiter(redis)
    app.state.settings = Settings.model_validate(
        original_settings.model_dump() | {"auth_password_reset_confirm_rate_limit": 2}
    )
    peer_client = TestClient(app, base_url=ORIGIN, client=(peer, 50000))
    try:
        headers = csrf_headers(peer_client)
        for expected in (400, 400, 429):
            response = peer_client.post(PATH, json=PAYLOAD, headers=headers)
            assert response.status_code == expected
            assert response.headers["cache-control"] == "no-store"
            assert "set-cookie" not in response.headers and TOKEN not in response.text
        assert 0 < int(response.headers["retry-after"]) <= 60
        assert redis.get(rate_key) == b"3" and 0 < cast(int, redis.ttl(rate_key)) <= 60
    finally:
        app.state.rate_limiter = original_limiter
        app.state.settings = original_settings
        redis.delete(rate_key)
        peer_client.close()
