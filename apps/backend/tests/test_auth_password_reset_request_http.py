import logging
from ipaddress import IPv6Address
from typing import cast
from unittest.mock import Mock, create_autospec
from uuid import uuid4

import pytest
from celery import Celery
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from redis import Redis
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

from app import main
from app.core.config import Settings
from app.modules.auth.application.dto import IssuedSession, PasswordResetDelivery
from app.modules.auth.application.password_recovery import PasswordRecoveryService
from app.modules.auth.application.ports import (
    EmailDeliveryUnavailable,
    EmailSender,
    RateLimiterUnavailable,
)
from app.modules.auth.domain.entities import TokenType
from app.modules.auth.infrastructure.email_sender import CeleryEmailSender, FakeEmailSender
from app.modules.auth.infrastructure.orm import CredentialModel, OneTimeTokenModel, SessionModel
from app.modules.auth.infrastructure.request_protection import RedisRateLimiter
from app.modules.auth.infrastructure.token_service import generate_token, hash_token
from app.modules.auth.presentation.dependencies import (
    get_current_session,
    get_email_sender,
    get_password_recovery,
)
from app.modules.users.infrastructure.orm import UserModel

PATH = "/api/v1/auth/password-reset/request"
EMAIL = "student@example.com"
ACK = {"detail": "Password reset request accepted."}
TOKEN = generate_token()


@pytest.fixture
def reset_service() -> Mock:
    service = create_autospec(PasswordRecoveryService, instance=True)
    service.request_reset.return_value = None
    return service


@pytest.fixture
def email_sender() -> Mock:
    return create_autospec(EmailSender, instance=True)


@pytest.fixture
def request_client(
    client: TestClient, application: FastAPI, reset_service: Mock, email_sender: Mock
) -> TestClient:
    application.dependency_overrides[get_password_recovery] = lambda: reset_service
    application.dependency_overrides[get_email_sender] = lambda: email_sender
    application.dependency_overrides.pop(get_current_session)
    return client


@pytest.fixture
def live_request_client(live_client: TestClient) -> TestClient:
    app = cast(FastAPI, live_client.app)
    app.state.settings = app.state.settings.model_copy(update={"auth_email_delivery_mode": "fake"})
    app.state.email_sender = FakeEmailSender()
    return live_client


@pytest.mark.parametrize("eligible", [False, True])
def test_request_acknowledges_without_login_and_queues_only_after_commit(
    request_client: TestClient,
    reset_service: Mock,
    email_sender: Mock,
    database: Mock,
    issued: IssuedSession,
    sessions: Mock,
    limiter: Mock,
    eligible: bool,
) -> None:
    if eligible:
        reset_service.request_reset.return_value = PasswordResetDelivery(
            issued.session.user_id, EMAIL, issued.session.expires_at, TOKEN
        )
    sequence: list[str] = []
    database.begin.return_value.__exit__.side_effect = lambda *args: sequence.append("commit")
    email_sender.send_password_reset.side_effect = lambda *args: sequence.append("queue")
    headers = csrf_headers(request_client) | {"X-Forwarded-For": "203.0.113.99"}
    request_client.cookies.set(SESSION_COOKIE, issued.token)
    response = request_client.post(PATH, json={"email": EMAIL}, headers=headers)
    assert response.status_code == 202 and response.json() == ACK
    assert response.headers["cache-control"] == "no-store" and "set-cookie" not in response.headers
    assert request_client.cookies.get(SESSION_COOKIE) == issued.token
    reset_service.request_reset.assert_called_once_with(EMAIL)
    assert sequence == (["commit", "queue"] if eligible else ["commit"])
    if eligible:
        email_sender.send_password_reset.assert_called_once_with(EMAIL, TOKEN)
    else:
        email_sender.send_password_reset.assert_not_called()
    sessions.validate.assert_not_called()
    limiter.check.assert_called_once_with(
        f"password-reset-request:{hash_token('192.0.2.10')}", 5, 60
    )
    assert EMAIL not in response.text and TOKEN not in response.text
    assert (
        "202" in request_client.get("/api/openapi.json").json()["paths"][PATH]["post"]["responses"]
    )


def test_after_commit_queue_failure_keeps_ack_and_logs_only_safe_metadata(
    request_client: TestClient,
    reset_service: Mock,
    email_sender: Mock,
    issued: IssuedSession,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Isolated migration fixtures configure logging and disable existing loggers.
    monkeypatch.setattr(
        logging.getLogger("app.modules.auth.presentation.routes"), "disabled", False
    )
    reset_service.request_reset.return_value = PasswordResetDelivery(
        issued.session.user_id, EMAIL, issued.session.expires_at, TOKEN
    )
    email_sender.send_password_reset.side_effect = EmailDeliveryUnavailable(EMAIL + TOKEN)
    with caplog.at_level(logging.WARNING):
        response = request_client.post(
            PATH, json={"email": EMAIL}, headers=csrf_headers(request_client)
        )
    assert response.status_code == 202 and response.json() == ACK
    assert "set-cookie" not in response.headers and response.headers["cache-control"] == "no-store"
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.__dict__["user_id"] == str(issued.session.user_id)
    assert record.__dict__["event"] == "auth.password_reset.email_queue_failed"
    assert record.exc_info is None
    assert TOKEN not in repr(record.__dict__) and EMAIL not in repr(record.__dict__)


@pytest.mark.parametrize("failure", ["database", "commit"])
def test_failed_transaction_never_queues_or_acknowledges(
    request_client: TestClient,
    reset_service: Mock,
    email_sender: Mock,
    database: Mock,
    failure: str,
) -> None:
    if failure == "database":
        reset_service.request_reset.side_effect = SQLAlchemyError(TOKEN)
    else:
        database.begin.return_value.__exit__.side_effect = SQLAlchemyError(TOKEN)
    response = request_client.post(
        PATH, json={"email": EMAIL}, headers=csrf_headers(request_client)
    )
    assert response.status_code == 503 and response.json() == {"detail": "Service unavailable."}
    assert TOKEN not in response.text and "set-cookie" not in response.headers
    email_sender.send_password_reset.assert_not_called()


@pytest.mark.parametrize("email", [EMAIL, "unknown@example.com"])
def test_disabled_delivery_precedes_account_lookup(
    request_client: TestClient,
    application: FastAPI,
    reset_service: Mock,
    database: Mock,
    email: str,
) -> None:
    application.dependency_overrides.pop(get_email_sender)
    application.state.settings = application.state.settings.model_copy(
        update={"auth_email_delivery_mode": "disabled"}
    )
    response = request_client.post(
        PATH, json={"email": email}, headers=csrf_headers(request_client)
    )
    assert response.status_code == 503 and response.json() == {"detail": "Service unavailable."}
    assert response.headers["cache-control"] == "no-store" and "set-cookie" not in response.headers
    reset_service.request_reset.assert_not_called()
    database.begin.assert_not_called()


@pytest.mark.parametrize("missing", ["Origin", "X-CSRF-Token"])
def test_request_csrf_precedes_rate_and_account_lookup(
    request_client: TestClient, reset_service: Mock, email_sender: Mock, limiter: Mock, missing: str
) -> None:
    headers = csrf_headers(request_client)
    headers.pop(missing)
    response = request_client.post(PATH, json={"email": EMAIL}, headers=headers)
    assert response.status_code == 403
    limiter.check.assert_not_called()
    reset_service.request_reset.assert_not_called()
    email_sender.send_password_reset.assert_not_called()


@pytest.mark.parametrize("outage", [False, True])
def test_request_rate_rejection_precedes_lookup(
    request_client: TestClient, reset_service: Mock, limiter: Mock, outage: bool
) -> None:
    if outage:
        limiter.check.side_effect = RateLimiterUnavailable(TOKEN)
    else:
        limiter.check.return_value = (False, 17)
    response = request_client.post(
        PATH, json={"email": EMAIL}, headers=csrf_headers(request_client)
    )
    assert response.status_code == (503 if outage else 429)
    assert TOKEN not in response.text and "set-cookie" not in response.headers
    assert response.headers["cache-control"] == "no-store"
    if not outage:
        assert response.headers["retry-after"] == "17"
    reset_service.request_reset.assert_not_called()


@pytest.mark.parametrize("body", ["type", "missing", "extra", "long", "empty", "json"])
def test_request_validation_is_generic(
    request_client: TestClient, reset_service: Mock, body: str
) -> None:
    headers = csrf_headers(request_client)
    if body == "json":
        response = request_client.post(
            PATH,
            content='{"email":"' + EMAIL,
            headers=headers | {"Content-Type": "application/json"},
        )
    else:
        payload = {
            "type": {"email": {"secret": EMAIL}},
            "missing": {},
            "extra": {"email": EMAIL, "token": TOKEN},
            "long": {"email": "x" * 321},
            "empty": {"email": ""},
        }[body]
        response = request_client.post(PATH, json=payload, headers=headers)
    assert response.status_code == 422 and response.json() == {"detail": "Invalid request."}
    assert EMAIL not in response.text and TOKEN not in response.text
    assert response.headers["cache-control"] == "no-store" and "set-cookie" not in response.headers
    reset_service.request_reset.assert_not_called()


@pytest.mark.parametrize(
    "field",
    ["auth_password_reset_request_rate_limit", "auth_password_reset_request_rate_window_seconds"],
)
def test_request_rate_settings_are_positive(browser_settings: Settings, field: str) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(browser_settings.model_dump() | {field: 0})


def test_api_manages_a_configured_celery_producer(
    browser_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    celery = create_autospec(Celery, instance=True)
    factory = Mock(return_value=celery)
    monkeypatch.setattr(main, "Celery", factory)
    with TestClient(main.create_app(browser_settings), base_url=ORIGIN) as client:
        app = cast(FastAPI, client.app)
        sender = app.state.email_sender
        assert isinstance(sender, CeleryEmailSender)
        assert sender.celery is celery and sender.settings is browser_settings
        factory.assert_called_once_with(
            "ukladen", broker=str(browser_settings.redis_url), set_as_current=False
        )
        assert celery.conf.update.call_args.kwargs["task_protocol"] == 2
        assert (
            celery.conf.update.call_args.kwargs["broker_transport_options"]["socket_timeout"] == 3
        )
        celery.close.assert_not_called()
    celery.close.assert_called_once_with()


@pytest.mark.parametrize("state", ["eligible", "unknown", "disabled", "no_credential", "malformed"])
def test_live_request_has_identical_responses_for_every_account_outcome(
    live_request_client: TestClient, concurrent_engine: Engine, password_hash: str, state: str
) -> None:
    seed_user(concurrent_engine, EMAIL, password_hash)
    session_token = browser_login(live_request_client)
    with Session(concurrent_engine) as database, database.begin():
        user = database.scalar(select(UserModel))
        assert user
        if state == "disabled":
            user.status = "disabled"
        elif state == "no_credential":
            database.execute(delete(CredentialModel))
    email = {
        "unknown": "unknown@example.com",
        "malformed": "Student <student@example.com>",
    }.get(state, " Student@EXAMPLE.COM ")
    response = live_request_client.post(
        PATH, json={"email": email}, headers=csrf_headers(live_request_client)
    )
    assert response.status_code == 202 and response.json() == ACK
    assert response.headers["cache-control"] == "no-store" and "set-cookie" not in response.headers
    assert live_request_client.cookies.get(SESSION_COOKIE) == session_token
    fake: FakeEmailSender = cast(FastAPI, live_request_client.app).state.email_sender
    assert len(fake.messages) == (1 if state == "eligible" else 0)
    with Session(concurrent_engine) as database:
        tokens = list(database.scalars(select(OneTimeTokenModel)))
        assert len(tokens) == (1 if state == "eligible" else 0)
        assert all(session.revoked_at is None for session in database.scalars(select(SessionModel)))
        if tokens:
            message = fake.messages[0]
            assert message.kind == TokenType.PASSWORD_RESET and message.email == EMAIL
            assert tokens[0].token_hash == hash_token(message.token.get_secret_value())
            assert tokens[0].used_at is None
            assert int((tokens[0].expires_at - tokens[0].created_at).total_seconds()) == 3600


def test_live_request_commit_then_confirm_and_login(
    live_request_client: TestClient,
    concurrent_engine: Engine,
    password_hash: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user(concurrent_engine, EMAIL, password_hash)
    current = browser_login(live_request_client)
    fake: FakeEmailSender = cast(FastAPI, live_request_client.app).state.email_sender
    original = fake.send_password_reset

    def check_committed_token(email: str, token: str) -> None:
        with Session(concurrent_engine) as database:
            stored = database.scalar(
                select(OneTimeTokenModel).where(OneTimeTokenModel.token_hash == hash_token(token))
            )
            assert stored and stored.used_at is None
        original(email, token)

    monkeypatch.setattr(fake, "send_password_reset", check_committed_token)
    headers = csrf_headers(live_request_client)
    request = live_request_client.post(PATH, json={"email": EMAIL}, headers=headers)
    assert request.status_code == 202 and request.json() == ACK
    assert live_request_client.cookies.get(SESSION_COOKIE) == current
    token = fake.messages[0].token.get_secret_value()
    assert token not in request.text
    live_request_client.cookies.delete(SESSION_COOKIE)
    confirm = live_request_client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": NEW_PASSWORD},
        headers=headers,
    )
    assert confirm.status_code == 204
    live_request_client.cookies.set(SESSION_COOKIE, current, domain="testserver.local", path="/")
    assert live_request_client.get("/api/v1/auth/sessions").status_code == 401
    for password, expected in ((PASSWORD, 401), (NEW_PASSWORD, 200)):
        response = live_request_client.post(
            "/api/v1/auth/login", json={"email": EMAIL, "password": password}, headers=headers
        )
        assert response.status_code == expected


def test_live_queue_failure_preserves_committed_token_and_retry_can_queue(
    live_request_client: TestClient,
    concurrent_engine: Engine,
    password_hash: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user(concurrent_engine, EMAIL, password_hash)
    fake: FakeEmailSender = cast(FastAPI, live_request_client.app).state.email_sender
    headers = csrf_headers(live_request_client)
    with monkeypatch.context() as patch:
        patch.setattr(
            fake, "send_password_reset", Mock(side_effect=EmailDeliveryUnavailable(TOKEN))
        )
        first = live_request_client.post(PATH, json={"email": EMAIL}, headers=headers)
    assert first.status_code == 202 and first.json() == ACK and not fake.messages
    with Session(concurrent_engine) as database:
        tokens = list(database.scalars(select(OneTimeTokenModel)))
        assert len(tokens) == 1 and tokens[0].used_at is None
        assert database.scalar(select(CredentialModel.password_hash)) == password_hash
    retry = live_request_client.post(PATH, json={"email": EMAIL}, headers=headers)
    assert retry.status_code == first.status_code and retry.content == first.content
    assert len(fake.messages) == 1
    with Session(concurrent_engine) as database:
        assert len(list(database.scalars(select(OneTimeTokenModel)))) == 2


def test_live_request_native_rate_window(live_request_client: TestClient) -> None:
    app = cast(FastAPI, live_request_client.app)
    redis: Redis = app.state.redis
    original_limiter = app.state.rate_limiter
    original_settings = app.state.settings
    peer = str(IPv6Address(uuid4().int))
    rate_key = f"ukladen:auth:rate:password-reset-request:{hash_token(peer)}"
    app.state.rate_limiter = RedisRateLimiter(redis)
    app.state.settings = Settings.model_validate(
        original_settings.model_dump() | {"auth_password_reset_request_rate_limit": 2}
    )
    peer_client = TestClient(app, base_url=ORIGIN, client=(peer, 50000))
    try:
        headers = csrf_headers(peer_client)
        for expected in (202, 202, 429):
            response = peer_client.post(
                PATH, json={"email": "unknown@example.com"}, headers=headers
            )
            assert response.status_code == expected
            assert (
                response.headers["cache-control"] == "no-store"
                and "set-cookie" not in response.headers
            )
        assert 0 < int(response.headers["retry-after"]) <= 60
        assert redis.get(rate_key) == b"3" and 0 < cast(int, redis.ttl(rate_key)) <= 60
    finally:
        app.state.rate_limiter = original_limiter
        app.state.settings = original_settings
        redis.delete(rate_key)
        peer_client.close()
