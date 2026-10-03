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
from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_auth_http import ORIGIN, SESSION_COOKIE, browser_login, csrf_headers, seed_user
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

from app.core.config import Settings
from app.modules.auth.application.dto import IssuedSession
from app.modules.auth.application.ports import RateLimiterUnavailable
from app.modules.auth.application.verification import EmailVerificationService
from app.modules.auth.domain.entities import TokenType
from app.modules.auth.domain.errors import InvalidOneTimeToken
from app.modules.auth.infrastructure.orm import OneTimeTokenModel, SessionModel
from app.modules.auth.infrastructure.request_protection import RedisRateLimiter
from app.modules.auth.infrastructure.token_service import generate_token, hash_token
from app.modules.auth.presentation.dependencies import get_current_session, get_email_verification
from app.modules.auth.presentation.schemas import EmailVerificationRequest
from app.modules.users.infrastructure.orm import UserModel
from app.modules.users.infrastructure.repository import SqlAlchemyEmailVerifier

PATH = "/api/v1/auth/email-verification/confirm"
TOKEN = "a" * 43


@pytest.fixture
def verification_service() -> Mock:
    return create_autospec(EmailVerificationService, instance=True)


@pytest.fixture
def verification_client(
    client: TestClient, application: FastAPI, verification_service: Mock
) -> TestClient:
    application.dependency_overrides[get_email_verification] = lambda: verification_service
    application.dependency_overrides.pop(get_current_session)
    return client


def test_confirmation_needs_no_login_and_retains_cookies(
    verification_client: TestClient,
    verification_service: Mock,
    limiter: Mock,
    sessions: Mock,
    issued: IssuedSession,
) -> None:
    headers = csrf_headers(verification_client) | {"X-Forwarded-For": "203.0.113.99"}
    for session_token in (None, issued.token):
        if session_token:
            verification_client.cookies.set(SESSION_COOKIE, session_token)
        response = verification_client.post(PATH, json={"token": TOKEN}, headers=headers)
        assert response.status_code == 204 and response.content == b""
        assert response.headers["cache-control"] == "no-store"
        assert "set-cookie" not in response.headers
        assert verification_client.cookies.get(SESSION_COOKIE) == session_token
    assert verification_service.confirm.call_count == 2
    verification_service.confirm.assert_called_with(TOKEN)
    limiter.check.assert_called_with(
        f"email-verification-confirm:{hash_token('192.0.2.10')}", 5, 60
    )
    sessions.validate.assert_not_called()
    payload = EmailVerificationRequest.model_validate({"token": TOKEN})
    assert TOKEN not in repr(payload) and TOKEN not in payload.model_dump_json()
    operation = verification_client.get("/api/openapi.json").json()["paths"][PATH]["post"]
    assert "204" in operation["responses"]


@pytest.mark.parametrize("failure", ["token", "database", "commit"])
def test_confirmation_errors_are_sanitized(
    verification_client: TestClient,
    verification_service: Mock,
    database: Mock,
    failure: str,
) -> None:
    if failure == "commit":
        database.begin.return_value.__exit__.side_effect = SQLAlchemyError(TOKEN)
    else:
        verification_service.confirm.side_effect = (
            InvalidOneTimeToken(TOKEN) if failure == "token" else SQLAlchemyError(TOKEN)
        )
    response = verification_client.post(
        PATH, json={"token": TOKEN}, headers=csrf_headers(verification_client)
    )
    assert response.status_code == (400 if failure == "token" else 503)
    assert response.json() == {
        "detail": "Invalid or expired token." if failure == "token" else "Service unavailable."
    }
    assert TOKEN not in response.text and "set-cookie" not in response.headers
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("missing", ["Origin", "X-CSRF-Token"])
def test_confirmation_csrf_precedes_rate_limit_and_service(
    verification_client: TestClient, verification_service: Mock, limiter: Mock, missing: str
) -> None:
    headers = csrf_headers(verification_client)
    headers.pop(missing)
    response = verification_client.post(PATH, json={"token": TOKEN}, headers=headers)
    assert response.status_code == 403
    limiter.check.assert_not_called()
    verification_service.confirm.assert_not_called()


@pytest.mark.parametrize("outage", [False, True])
def test_confirmation_rate_rejection_precedes_service(
    verification_client: TestClient, verification_service: Mock, limiter: Mock, outage: bool
) -> None:
    if outage:
        limiter.check.side_effect = RateLimiterUnavailable(TOKEN)
    else:
        limiter.check.return_value = (False, 17)
    response = verification_client.post(
        PATH, json={"token": TOKEN}, headers=csrf_headers(verification_client)
    )
    assert response.status_code == (503 if outage else 429)
    assert TOKEN not in response.text and "set-cookie" not in response.headers
    assert response.headers["cache-control"] == "no-store"
    if not outage:
        assert response.headers["retry-after"] == "17"
    verification_service.confirm.assert_not_called()


@pytest.mark.parametrize("body", ["type", "missing", "extra", "short", "long", "json"])
def test_confirmation_validation_never_echoes_token(
    verification_client: TestClient, verification_service: Mock, body: str
) -> None:
    headers = csrf_headers(verification_client)
    if body == "json":
        response = verification_client.post(
            PATH,
            content='{"token":"' + TOKEN,
            headers=headers | {"Content-Type": "application/json"},
        )
    else:
        payload = {
            "type": {"token": {"secret": TOKEN}},
            "missing": {},
            "extra": {"token": TOKEN, "extra": TOKEN},
            "short": {"token": TOKEN[:-1]},
            "long": {"token": TOKEN + "a"},
        }[body]
        response = verification_client.post(PATH, json=payload, headers=headers)
    assert response.status_code == 422 and response.json() == {"detail": "Invalid request."}
    assert TOKEN not in response.text and "set-cookie" not in response.headers
    assert response.headers["cache-control"] == "no-store"
    verification_service.confirm.assert_not_called()


@pytest.mark.parametrize(
    "field",
    [
        "auth_email_verification_confirm_rate_limit",
        "auth_email_verification_confirm_rate_window_seconds",
    ],
)
def test_confirmation_rate_settings_are_positive(browser_settings: Settings, field: str) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(browser_settings.model_dump() | {field: 0})


def seed_token(database: Session, user_id: UUID) -> tuple[UUID, str]:
    raw_token = generate_token()
    now = datetime.now(UTC)
    token = OneTimeTokenModel(
        user_id=user_id,
        token_type=TokenType.EMAIL_VERIFICATION,
        token_hash=hash_token(raw_token),
        created_at=now - timedelta(hours=1),
        expires_at=now + timedelta(hours=1),
    )
    database.add(token)
    database.flush()
    return token.id, raw_token


@pytest.mark.parametrize("already_verified", [False, True])
def test_live_confirmation_retains_session_and_prior_verification(
    live_client: TestClient, concurrent_engine: Engine, password_hash: str, already_verified: bool
) -> None:
    seed_user(concurrent_engine, "student@example.com", password_hash)
    session_token = browser_login(live_client)
    previous = datetime.now(UTC) - timedelta(days=1) if already_verified else None
    with Session(concurrent_engine) as database, database.begin():
        user = database.scalar(select(UserModel))
        assert user
        user.email_verified_at = previous
        user.status = "disabled" if already_verified else "active"
        token_id, raw_token = seed_token(database, user.id)
    headers = csrf_headers(live_client)
    response = live_client.post(PATH, json={"token": raw_token}, headers=headers)
    assert response.status_code == 204 and response.content == b""
    assert "set-cookie" not in response.headers
    assert live_client.cookies.get(SESSION_COOKIE) == session_token
    with Session(concurrent_engine) as database:
        stored = database.get(OneTimeTokenModel, token_id)
        user = database.scalar(select(UserModel))
        session = database.scalar(select(SessionModel))
        assert stored and stored.used_at
        assert user and user.email_verified_at == (previous or stored.used_at)
        assert user.status == ("disabled" if already_verified else "active")
        assert (
            session
            and session.revoked_at is None
            and session.token_hash == hash_token(session_token)
        )
    replay = live_client.post(PATH, json={"token": raw_token}, headers=headers)
    assert replay.status_code == 400 and replay.json() == {"detail": "Invalid or expired token."}
    assert raw_token not in replay.text and "set-cookie" not in replay.headers


@pytest.mark.parametrize(
    "state", ["unknown", "malformed", "expired", "future", "used", "wrong_type"]
)
def test_live_invalid_tokens_leave_user_and_token_unchanged(
    live_client: TestClient, concurrent_engine: Engine, state: str
) -> None:
    used_at = None
    with Session(concurrent_engine) as database, database.begin():
        user = UserModel(email="verification@example.com")
        database.add(user)
        database.flush()
        token_id, raw_token = seed_token(database, user.id)
        token = database.get(OneTimeTokenModel, token_id)
        assert token
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
        else:
            token.token_type = TokenType.PASSWORD_RESET
    response = live_client.post(PATH, json={"token": raw_token}, headers=csrf_headers(live_client))
    assert response.status_code == 400 and response.json() == {
        "detail": "Invalid or expired token."
    }
    assert raw_token not in response.text and "set-cookie" not in response.headers
    with Session(concurrent_engine) as database:
        token = database.get(OneTimeTokenModel, token_id)
        user = database.scalar(select(UserModel))
        assert token and token.used_at == used_at
        assert user and user.email_verified_at is None and user.status == "active"


def test_live_late_user_update_failure_rolls_back_and_allows_retry(
    live_client: TestClient, concurrent_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with Session(concurrent_engine) as database, database.begin():
        user = UserModel(email="verification@example.com")
        database.add(user)
        database.flush()
        token_id, raw_token = seed_token(database, user.id)
    original = SqlAlchemyEmailVerifier.mark_verified

    def fail_after_update(
        self: SqlAlchemyEmailVerifier, user_id: UUID, verified_at: datetime
    ) -> bool:
        original(self, user_id, verified_at)
        raise SQLAlchemyError(raw_token)

    headers = csrf_headers(live_client)
    with monkeypatch.context() as patch:
        patch.setattr(SqlAlchemyEmailVerifier, "mark_verified", fail_after_update)
        response = live_client.post(PATH, json={"token": raw_token}, headers=headers)
    assert response.status_code == 503 and response.json() == {"detail": "Service unavailable."}
    assert raw_token not in response.text and "set-cookie" not in response.headers
    with Session(concurrent_engine) as database:
        token = database.get(OneTimeTokenModel, token_id)
        user = database.scalar(select(UserModel))
        assert token and token.used_at is None
        assert user and user.email_verified_at is None
    assert live_client.post(PATH, json={"token": raw_token}, headers=headers).status_code == 204
    with Session(concurrent_engine) as database:
        token = database.get(OneTimeTokenModel, token_id)
        user = database.scalar(select(UserModel))
        assert token and token.used_at
        assert user and user.email_verified_at == token.used_at


def test_live_confirmation_native_rate_window(
    live_client: TestClient, concurrent_engine: Engine
) -> None:
    app = cast(FastAPI, live_client.app)
    redis: Redis = app.state.redis
    original_limiter = app.state.rate_limiter
    peer = str(IPv6Address(uuid4().int))
    rate_key = f"ukladen:auth:rate:email-verification-confirm:{hash_token(peer)}"
    with Session(concurrent_engine) as database, database.begin():
        user = UserModel(email="verification@example.com")
        database.add(user)
        database.flush()
        _, raw_token = seed_token(database, user.id)
    app.state.rate_limiter = RedisRateLimiter(redis)
    # Reuse the running app with a unique peer so this test owns its Redis rate key.
    peer_client = TestClient(app, base_url=ORIGIN, client=(peer, 50000))
    try:
        headers = csrf_headers(peer_client)
        for expected in (204, 400, 400, 400, 400, 429):
            response = peer_client.post(PATH, json={"token": raw_token}, headers=headers)
            assert response.status_code == expected
            assert response.headers["cache-control"] == "no-store"
            assert "set-cookie" not in response.headers and raw_token not in response.text
        assert 0 < int(response.headers["retry-after"]) <= 60
        assert redis.get(rate_key) == b"6"
        assert 0 < cast(int, redis.ttl(rate_key)) <= 60
    finally:
        app.state.rate_limiter = original_limiter
        redis.delete(rate_key)
        peer_client.close()
