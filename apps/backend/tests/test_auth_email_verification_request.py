import logging
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import Mock, create_autospec
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from redis import Redis
from sqlalchemy import Engine, select, text, update
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session
from test_auth_http import SESSION_COOKIE, browser_login, csrf_headers, seed_user
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
from app.modules.auth.application.dto import EmailVerificationDelivery, IssuedSession
from app.modules.auth.application.ports import (
    EmailDeliveryUnavailable,
    EmailSender,
    RateLimiterUnavailable,
    RegistrationRepository,
)
from app.modules.auth.application.verification_request import EmailVerificationRequestService
from app.modules.auth.domain.entities import OneTimeToken
from app.modules.auth.infrastructure.email_sender import FakeEmailSender
from app.modules.auth.infrastructure.orm import OneTimeTokenModel, SessionModel
from app.modules.auth.infrastructure.repository import SqlAlchemyRegistrationRepository
from app.modules.auth.infrastructure.request_protection import RedisRateLimiter
from app.modules.auth.infrastructure.token_service import generate_token, hash_token
from app.modules.auth.presentation.dependencies import (
    get_current_session,
    get_email_sender,
    get_email_verification_request,
)
from app.modules.users.application.ports import EmailVerifier
from app.modules.users.infrastructure.orm import UserModel
from app.modules.users.infrastructure.repository import SqlAlchemyEmailVerifier

PATH = "/api/v1/auth/email-verification/request"
EMAIL = "student@example.com"
ACK = {"detail": "Email verification request accepted."}
NOW = datetime(2026, 10, 3, tzinfo=UTC)
TOKEN = generate_token()


@pytest.mark.parametrize("eligible", [False, True])
def test_request_application_uses_locked_email_and_configured_lifetime(
    settings: Settings, eligible: bool
) -> None:
    users = create_autospec(EmailVerifier, instance=True)
    repository = create_autospec(RegistrationRepository, instance=True)
    clock = Mock(return_value=NOW)
    generator = Mock(return_value=TOKEN)

    def locked_email(user_id: UUID) -> str | None:
        clock.assert_not_called()
        generator.assert_not_called()
        return EMAIL if eligible else None

    users.get_unverified_email.side_effect = locked_email
    service = EmailVerificationRequestService(
        users,
        repository,
        settings.model_copy(update={"auth_email_verification_ttl_seconds": 120}),
        generate_token=generator,
        hash_token=hash_token,
        now=clock,
    )
    user_id = uuid4()
    result = service.request(user_id)
    users.get_unverified_email.assert_called_once_with(user_id)
    if eligible:
        assert (
            result and result.user_id == user_id and result.email == EMAIL and result.token == TOKEN
        )
        assert result.expires_at == NOW + timedelta(seconds=120) and TOKEN not in repr(result)
        stored = repository.create_one_time_token.call_args.args[0]
        assert stored.token_hash == hash_token(TOKEN) and stored.user_id == user_id
        assert stored.token_type.value == "email_verification" and stored.created_at == NOW
        assert stored.expires_at == result.expires_at and stored.used_at is None
    else:
        assert result is None and not repository.mock_calls
        clock.assert_not_called()
        generator.assert_not_called()
    users.mark_verified.assert_not_called()


@pytest.fixture
def verification_request_service(issued: IssuedSession) -> Mock:
    service = create_autospec(EmailVerificationRequestService, instance=True)
    service.request.return_value = EmailVerificationDelivery(
        issued.session.user_id, EMAIL, issued.session.expires_at, TOKEN
    )
    return service


@pytest.fixture
def email_sender() -> Mock:
    return create_autospec(EmailSender, instance=True)


@pytest.fixture
def request_client(
    client: TestClient, application: FastAPI, verification_request_service: Mock, email_sender: Mock
) -> TestClient:
    application.dependency_overrides[get_email_verification_request] = lambda: (
        verification_request_service
    )
    application.dependency_overrides[get_email_sender] = lambda: email_sender
    return client


@pytest.fixture
def live_request_client(live_client: TestClient) -> TestClient:
    app = cast(FastAPI, live_client.app)
    app.state.settings = app.state.settings.model_copy(update={"auth_email_delivery_mode": "fake"})
    app.state.email_sender = FakeEmailSender()
    return live_client


@pytest.mark.parametrize("eligible", [False, True])
def test_http_request_uses_current_user_and_commits_before_queue(
    request_client: TestClient,
    verification_request_service: Mock,
    email_sender: Mock,
    database: Mock,
    issued: IssuedSession,
    limiter: Mock,
    eligible: bool,
) -> None:
    if not eligible:
        verification_request_service.request.return_value = None
    sequence: list[str] = []
    database.begin.return_value.__exit__.side_effect = lambda *args: sequence.append("commit")
    email_sender.send_email_verification.side_effect = lambda *args: sequence.append("queue")
    request_client.cookies.set(SESSION_COOKIE, issued.token)
    response = request_client.post(PATH, json={}, headers=csrf_headers(request_client))
    assert response.status_code == 202 and response.json() == ACK
    assert "set-cookie" not in response.headers and response.headers["cache-control"] == "no-store"
    assert request_client.cookies.get(SESSION_COOKIE) == issued.token
    assert sequence == (["commit", "queue"] if eligible else ["commit"])
    verification_request_service.request.assert_called_once_with(issued.session.user_id)
    limiter.check.assert_called_once_with(
        f"email-verification-request:{issued.session.user_id}", 5, 60
    )
    if eligible:
        email_sender.send_email_verification.assert_called_once_with(EMAIL, TOKEN)
    else:
        email_sender.send_email_verification.assert_not_called()
    assert TOKEN not in response.text and EMAIL not in response.text
    assert (
        "202" in request_client.get("/api/openapi.json").json()["paths"][PATH]["post"]["responses"]
    )


@pytest.mark.parametrize("commit_failure", [False, True])
def test_http_database_failure_prevents_queue(
    request_client: TestClient,
    verification_request_service: Mock,
    email_sender: Mock,
    database: Mock,
    commit_failure: bool,
) -> None:
    if commit_failure:
        database.begin.return_value.__exit__.side_effect = SQLAlchemyError(TOKEN)
    else:
        verification_request_service.request.side_effect = SQLAlchemyError(TOKEN)
    response = request_client.post(PATH, json={}, headers=csrf_headers(request_client))
    assert response.status_code == 503 and response.json() == {"detail": "Service unavailable."}
    assert TOKEN not in response.text and "set-cookie" not in response.headers
    email_sender.send_email_verification.assert_not_called()


def test_http_disabled_delivery_prevents_issuance(
    request_client: TestClient,
    application: FastAPI,
    verification_request_service: Mock,
    database: Mock,
) -> None:
    application.dependency_overrides.pop(get_email_sender)
    response = request_client.post(PATH, json={}, headers=csrf_headers(request_client))
    assert response.status_code == 503
    verification_request_service.request.assert_not_called()
    database.begin.assert_not_called()


def test_http_requires_authentication_before_limiter_and_issuance(
    request_client: TestClient,
    application: FastAPI,
    verification_request_service: Mock,
    limiter: Mock,
) -> None:
    application.dependency_overrides.pop(get_current_session)
    response = request_client.post(PATH, json={}, headers=csrf_headers(request_client))
    assert response.status_code == 401
    verification_request_service.request.assert_not_called()
    limiter.check.assert_not_called()


@pytest.mark.parametrize("missing", ["Origin", "X-CSRF-Token"])
def test_http_csrf_precedes_rate_and_issuance(
    request_client: TestClient, verification_request_service: Mock, limiter: Mock, missing: str
) -> None:
    headers = csrf_headers(request_client)
    headers.pop(missing)
    assert request_client.post(PATH, json={}, headers=headers).status_code == 403
    verification_request_service.request.assert_not_called()
    limiter.check.assert_not_called()


@pytest.mark.parametrize("outage", [False, True])
def test_http_rate_limit_precedes_issuance(
    request_client: TestClient, verification_request_service: Mock, limiter: Mock, outage: bool
) -> None:
    limiter.check.side_effect = RateLimiterUnavailable(TOKEN) if outage else None
    limiter.check.return_value = (False, 17)
    response = request_client.post(PATH, json={}, headers=csrf_headers(request_client))
    assert response.status_code == (503 if outage else 429)
    assert "set-cookie" not in response.headers and TOKEN not in response.text
    assert response.headers["cache-control"] == "no-store"
    if not outage:
        assert response.headers["retry-after"] == "17"
    verification_request_service.request.assert_not_called()


@pytest.mark.parametrize(
    "body", [{"email": EMAIL}, {"user_id": str(uuid4())}, {"token": TOKEN}, [], None, "malformed"]
)
def test_http_rejects_caller_recipient_and_invalid_transport(
    request_client: TestClient, verification_request_service: Mock, body: object
) -> None:
    headers = csrf_headers(request_client)
    if body == "malformed":
        response = request_client.post(
            PATH,
            content='{"token":"' + TOKEN,
            headers=headers | {"Content-Type": "application/json"},
        )
    else:
        response = request_client.post(PATH, json=body, headers=headers)
    assert response.status_code == 422 and response.json() == {"detail": "Invalid request."}
    assert (
        TOKEN not in response.text
        and EMAIL not in response.text
        and "set-cookie" not in response.headers
    )
    verification_request_service.request.assert_not_called()


def test_http_queue_failure_is_acknowledged_without_secret_logs(
    request_client: TestClient,
    email_sender: Mock,
    issued: IssuedSession,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        logging.getLogger("app.modules.auth.presentation.routes"), "disabled", False
    )
    email_sender.send_email_verification.side_effect = EmailDeliveryUnavailable(EMAIL + TOKEN)
    with caplog.at_level(logging.WARNING):
        response = request_client.post(PATH, json={}, headers=csrf_headers(request_client))
    assert (
        response.status_code == 202
        and response.json() == ACK
        and "set-cookie" not in response.headers
    )
    record = next(
        record
        for record in caplog.records
        if record.getMessage() == "Email verification queue failed."
    )
    assert record.__dict__["user_id"] == str(issued.session.user_id)
    assert (
        record.__dict__["event"] == "auth.email_verification.email_queue_failed"
        and record.exc_info is None
    )
    for secret in (EMAIL, TOKEN, issued.token):
        assert secret not in repr(record.__dict__)


@pytest.mark.parametrize(
    "field",
    [
        "auth_email_verification_request_rate_limit",
        "auth_email_verification_request_rate_window_seconds",
    ],
)
def test_request_rate_settings_are_positive(browser_settings: Settings, field: str) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(browser_settings.model_dump() | {field: 0})


def test_live_resend_then_confirmation_preserves_prior_tokens_and_sessions(
    live_request_client: TestClient,
    concurrent_engine: Engine,
    password_hash: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user(concurrent_engine, EMAIL, password_hash)
    seed_user(concurrent_engine, "other@example.com", password_hash)
    session_token = browser_login(live_request_client)
    app = cast(FastAPI, live_request_client.app)
    sender: FakeEmailSender = app.state.email_sender
    original = sender.send_email_verification

    def check_committed(email: str, token: str) -> None:
        with Session(concurrent_engine) as database:
            stored = database.scalar(
                select(OneTimeTokenModel).where(OneTimeTokenModel.token_hash == hash_token(token))
            )
            assert stored and stored.used_at is None and stored.token_type == "email_verification"
            assert (stored.expires_at - stored.created_at).total_seconds() == 86400
            user = database.get(UserModel, stored.user_id)
            assert user and user.email == email == EMAIL and user.email_verified_at is None
        original(email, token)

    monkeypatch.setattr(sender, "send_email_verification", check_committed)
    headers = csrf_headers(live_request_client)
    for _ in range(2):
        response = live_request_client.post(PATH, json={}, headers=headers)
        assert (
            response.status_code == 202
            and response.json() == ACK
            and "set-cookie" not in response.headers
        )
    assert len(sender.messages) == 2
    tokens = [message.token.get_secret_value() for message in sender.messages]
    assert tokens[0] != tokens[1]
    for token in tokens:
        assert (
            live_request_client.post(
                "/api/v1/auth/email-verification/confirm", json={"token": token}, headers=headers
            ).status_code
            == 204
        )
        assert (
            live_request_client.post(
                "/api/v1/auth/email-verification/confirm", json={"token": token}, headers=headers
            ).status_code
            == 400
        )
    assert live_request_client.post(PATH, json={}, headers=headers).json() == ACK
    assert (
        len(sender.messages) == 2
        and live_request_client.cookies.get(SESSION_COOKIE) == session_token
    )
    with Session(concurrent_engine) as database:
        assert len(list(database.scalars(select(OneTimeTokenModel)))) == 2
        other = database.scalar(select(UserModel).where(UserModel.email == "other@example.com"))
        session = database.scalar(select(SessionModel))
        assert other and other.email_verified_at is None and session and session.revoked_at is None
    assert live_request_client.get("/api/v1/auth/sessions").status_code == 200


@pytest.mark.parametrize("failure", ["database", "queue", "disabled_user", "disabled_delivery"])
def test_live_resend_failure_and_retry(
    live_request_client: TestClient,
    concurrent_engine: Engine,
    password_hash: str,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    seed_user(concurrent_engine, EMAIL, password_hash)
    session_token = browser_login(live_request_client)
    app = cast(FastAPI, live_request_client.app)
    sender: FakeEmailSender = app.state.email_sender
    original = sender.send_email_verification

    def fail(*args: object) -> None:
        raise EmailDeliveryUnavailable(TOKEN)

    def fail_after_insert(
        repository: SqlAlchemyRegistrationRepository, token: OneTimeToken
    ) -> None:
        original_insert(repository, token)
        raise SQLAlchemyError(TOKEN)

    original_insert = SqlAlchemyRegistrationRepository.create_one_time_token
    if failure == "database":
        monkeypatch.setattr(
            SqlAlchemyRegistrationRepository, "create_one_time_token", fail_after_insert
        )
    elif failure == "queue":
        monkeypatch.setattr(sender, "send_email_verification", fail)
    elif failure == "disabled_user":
        with Session(concurrent_engine) as database, database.begin():
            database.execute(update(UserModel).values(status="disabled"))
    else:
        app.state.settings = app.state.settings.model_copy(
            update={"auth_email_delivery_mode": "disabled"}
        )
    response = live_request_client.post(PATH, json={}, headers=csrf_headers(live_request_client))
    assert (
        response.status_code
        == {"database": 503, "queue": 202, "disabled_user": 401, "disabled_delivery": 503}[failure]
    )
    assert not sender.messages and TOKEN not in response.text
    if failure != "disabled_user":
        assert (
            "set-cookie" not in response.headers
            and live_request_client.cookies.get(SESSION_COOKIE) == session_token
        )
    with Session(concurrent_engine) as database:
        stored = list(database.scalars(select(OneTimeTokenModel)))
        assert len(stored) == (1 if failure == "queue" else 0)
        assert all(token.used_at is None for token in stored)
    if failure in {"database", "queue"}:
        monkeypatch.setattr(
            SqlAlchemyRegistrationRepository, "create_one_time_token", original_insert
        )
        monkeypatch.setattr(sender, "send_email_verification", original)
        retry = live_request_client.post(PATH, json={}, headers=csrf_headers(live_request_client))
        assert retry.status_code == 202 and retry.json() == ACK and len(sender.messages) == 1
        with Session(concurrent_engine) as database:
            assert len(list(database.scalars(select(OneTimeTokenModel)))) == (
                2 if failure == "queue" else 1
            )


@pytest.mark.parametrize("state", ["missing", "disabled", "verified", "eligible"])
def test_live_user_adapter_eligibility_and_lock(concurrent_engine: Engine, state: str) -> None:
    with Session(concurrent_engine) as database, database.begin():
        user = UserModel(
            email=EMAIL,
            status="disabled" if state == "disabled" else "active",
            email_verified_at=NOW if state == "verified" else None,
        )
        database.add(user)
        database.flush()
        user_id = uuid4() if state == "missing" else user.id
    with Session(concurrent_engine) as owner:
        assert SqlAlchemyEmailVerifier(owner).get_unverified_email(user_id) == (
            EMAIL if state == "eligible" else None
        )
        if state == "eligible":
            with (
                Session(concurrent_engine) as contender,
                pytest.raises(OperationalError, match="lock timeout"),
                contender.begin(),
            ):
                contender.execute(text("SET LOCAL lock_timeout = '100ms'"))
                SqlAlchemyEmailVerifier(contender).mark_verified(user_id, NOW)
        owner.commit()
    if state == "eligible":
        with Session(concurrent_engine) as database, database.begin():
            assert SqlAlchemyEmailVerifier(database).mark_verified(user_id, NOW)
        with Session(concurrent_engine) as database:
            assert SqlAlchemyEmailVerifier(database).get_unverified_email(user_id) is None


def test_live_resend_per_user_redis_window(
    live_request_client: TestClient, concurrent_engine: Engine, password_hash: str
) -> None:
    seed_user(concurrent_engine, EMAIL, password_hash)
    seed_user(concurrent_engine, "other@example.com", password_hash)
    browser_login(live_request_client)
    app = cast(FastAPI, live_request_client.app)
    app.state.settings = app.state.settings.model_copy(
        update={"auth_email_verification_request_rate_limit": 2}
    )
    app.state.rate_limiter = RedisRateLimiter(app.state.redis)
    redis: Redis = app.state.redis
    keys: list[str] = []
    try:
        with Session(concurrent_engine) as database:
            keys = [
                f"ukladen:auth:rate:email-verification-request:{user_id}"
                for user_id in database.scalars(
                    select(UserModel.id).order_by(UserModel.email.desc())
                )
            ]
        headers = csrf_headers(live_request_client)
        for expected in (202, 202, 429):
            response = live_request_client.post(PATH, json={}, headers=headers)
            assert response.status_code == expected
        assert 0 < int(response.headers["retry-after"]) <= 60
        assert redis.get(keys[0]) == b"3" and 0 < cast(int, redis.ttl(keys[0])) <= 60
        browser_login(live_request_client, "other@example.com")
        assert live_request_client.post(PATH, json={}, headers=headers).status_code == 202
        assert redis.get(keys[1]) == b"1"
    finally:
        if keys:
            redis.delete(*keys)
