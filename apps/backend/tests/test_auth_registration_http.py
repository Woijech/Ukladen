import logging
from http.cookies import SimpleCookie
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
from test_auth_http import ORIGIN, PASSWORD, SESSION_COOKIE, browser_login, csrf_headers
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
from app.modules.auth.application.dto import IssuedSession, RegistrationResult
from app.modules.auth.application.ports import (
    EmailDeliveryUnavailable,
    EmailSender,
    RateLimiterUnavailable,
)
from app.modules.auth.application.registration import RegistrationService
from app.modules.auth.domain.errors import InvalidRegistration, RegistrationConflict
from app.modules.auth.infrastructure.email_sender import FakeEmailSender
from app.modules.auth.infrastructure.orm import (
    CredentialModel,
    IdentityModel,
    OneTimeTokenModel,
    SessionModel,
)
from app.modules.auth.infrastructure.password_hasher import Argon2PasswordHasher
from app.modules.auth.infrastructure.request_protection import RedisRateLimiter
from app.modules.auth.infrastructure.token_service import generate_token, hash_token
from app.modules.auth.presentation.dependencies import (
    get_current_session,
    get_email_sender,
    get_registration,
)
from app.modules.auth.presentation.schemas import RegistrationRequest
from app.modules.users.infrastructure.orm import UserModel

PATH = "/api/v1/auth/register"
EMAIL = "student@example.com"
TOKEN = generate_token()


@pytest.fixture
def registration_service(issued: IssuedSession) -> Mock:
    service = create_autospec(RegistrationService, instance=True)
    service.register.return_value = RegistrationResult(issued.session.user_id, EMAIL, issued, TOKEN)
    return service


@pytest.fixture
def email_sender() -> Mock:
    return create_autospec(EmailSender, instance=True)


@pytest.fixture
def registration_client(
    client: TestClient, application: FastAPI, registration_service: Mock, email_sender: Mock
) -> TestClient:
    application.dependency_overrides[get_registration] = lambda: registration_service
    application.dependency_overrides[get_email_sender] = lambda: email_sender
    application.dependency_overrides.pop(get_current_session)
    return client


@pytest.fixture
def live_registration_client(live_client: TestClient) -> TestClient:
    app = cast(FastAPI, live_client.app)
    app.state.settings = app.state.settings.model_copy(update={"auth_email_delivery_mode": "fake"})
    app.state.email_sender = FakeEmailSender()
    return live_client


def test_registration_commits_before_cookie_and_email(
    registration_client: TestClient,
    registration_service: Mock,
    email_sender: Mock,
    database: Mock,
    issued: IssuedSession,
    sessions: Mock,
    limiter: Mock,
    browser_settings: Settings,
) -> None:
    sequence: list[str] = []
    database.begin.return_value.__exit__.side_effect = lambda *args: sequence.append("commit")
    email_sender.send_email_verification.side_effect = lambda *args: sequence.append("queue")
    headers = csrf_headers(registration_client) | {
        "User-Agent": "a" * 1500,
        "X-Forwarded-For": "203.0.113.99",
    }
    registration_client.cookies.set(SESSION_COOKIE, "invalid-session")
    response = registration_client.post(
        PATH, json={"email": EMAIL, "password": PASSWORD}, headers=headers
    )
    assert response.status_code == 201 and sequence == ["commit", "queue"]
    assert response.json() == {
        "user_id": str(issued.session.user_id),
        "session_id": str(issued.session.id),
        "expires_at": issued.session.expires_at.isoformat().replace("+00:00", "Z"),
    }
    assert response.headers["cache-control"] == "no-store"
    parsed = SimpleCookie()
    parsed.load(response.headers["set-cookie"])
    cookie = parsed[SESSION_COOKIE]
    assert cookie["httponly"] and cookie["secure"] and cookie["samesite"] == "lax"
    assert cookie["path"] == "/" and not cookie["domain"] and cookie["expires"]
    assert int(cookie["max-age"]) == browser_settings.auth_session_ttl_seconds
    assert cookie.value == issued.token
    assert registration_service.register.call_args.args == (EMAIL, PASSWORD)
    assert registration_service.register.call_args.kwargs["user_agent"] == "a" * 1024
    assert str(registration_service.register.call_args.kwargs["ip_address"]) == "192.0.2.10"
    email_sender.send_email_verification.assert_called_once_with(EMAIL, TOKEN)
    limiter.check.assert_called_once_with(f"register:{hash_token('192.0.2.10')}", 5, 60)
    sessions.validate.assert_not_called()
    for secret in (PASSWORD, TOKEN, issued.token, issued.session.token_hash):
        assert secret not in response.text
    assert (
        "201"
        in registration_client.get("/api/openapi.json").json()["paths"][PATH]["post"]["responses"]
    )
    dto = RegistrationRequest.model_validate({"email": EMAIL, "password": PASSWORD})
    assert PASSWORD not in repr(dto) and PASSWORD not in dto.model_dump_json()


@pytest.mark.parametrize("failure", ["input", "conflict", "database", "commit"])
def test_registration_failure_never_queues_or_issues_cookie(
    registration_client: TestClient,
    registration_service: Mock,
    email_sender: Mock,
    database: Mock,
    failure: str,
) -> None:
    if failure == "commit":
        database.begin.return_value.__exit__.side_effect = SQLAlchemyError(TOKEN)
    else:
        registration_service.register.side_effect = {
            "input": InvalidRegistration(TOKEN),
            "conflict": RegistrationConflict(TOKEN),
            "database": SQLAlchemyError(TOKEN),
        }[failure]
    response = registration_client.post(
        PATH, json={"email": EMAIL, "password": PASSWORD}, headers=csrf_headers(registration_client)
    )
    status, detail = {
        "input": (400, "Invalid registration input."),
        "conflict": (409, "Registration could not be completed."),
        "database": (503, "Service unavailable."),
        "commit": (503, "Service unavailable."),
    }[failure]
    assert response.status_code == status and response.json() == {"detail": detail}
    assert response.headers["cache-control"] == "no-store" and "set-cookie" not in response.headers
    assert TOKEN not in response.text and PASSWORD not in response.text
    email_sender.send_email_verification.assert_not_called()


def test_registration_queue_failure_retains_success_and_safe_log(
    registration_client: TestClient,
    email_sender: Mock,
    issued: IssuedSession,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        logging.getLogger("app.modules.auth.presentation.routes"), "disabled", False
    )
    email_sender.send_email_verification.side_effect = EmailDeliveryUnavailable(
        EMAIL + TOKEN + PASSWORD
    )
    with caplog.at_level(logging.WARNING):
        response = registration_client.post(
            PATH,
            json={"email": EMAIL, "password": PASSWORD},
            headers=csrf_headers(registration_client),
        )
    assert (
        response.status_code == 201
        and registration_client.cookies.get(SESSION_COOKIE) == issued.token
    )
    record = next(
        record
        for record in caplog.records
        if record.getMessage() == "Registration email queue failed."
    )
    assert (
        record.__dict__["user_id"] == str(issued.session.user_id)
        and record.__dict__["event"] == "auth.registration.email_queue_failed"
    )
    assert record.exc_info is None
    for secret in (EMAIL, TOKEN, PASSWORD, issued.token):
        assert secret not in repr(record.__dict__)


def test_disabled_email_prevents_registration(
    registration_client: TestClient,
    application: FastAPI,
    registration_service: Mock,
    database: Mock,
) -> None:
    application.dependency_overrides.pop(get_email_sender)
    response = registration_client.post(
        PATH, json={"email": EMAIL, "password": PASSWORD}, headers=csrf_headers(registration_client)
    )
    assert response.status_code == 503 and response.json() == {"detail": "Service unavailable."}
    assert "set-cookie" not in response.headers
    registration_service.register.assert_not_called()
    database.begin.assert_not_called()


@pytest.mark.parametrize("missing", ["Origin", "X-CSRF-Token"])
def test_registration_csrf_precedes_mutation(
    registration_client: TestClient,
    registration_service: Mock,
    email_sender: Mock,
    limiter: Mock,
    missing: str,
) -> None:
    headers = csrf_headers(registration_client)
    headers.pop(missing)
    response = registration_client.post(
        PATH, json={"email": EMAIL, "password": PASSWORD}, headers=headers
    )
    assert response.status_code == 403 and "set-cookie" not in response.headers
    registration_service.register.assert_not_called()
    email_sender.send_email_verification.assert_not_called()
    limiter.check.assert_not_called()


@pytest.mark.parametrize("outage", [False, True])
def test_registration_rate_protection_precedes_mutation(
    registration_client: TestClient,
    registration_service: Mock,
    email_sender: Mock,
    limiter: Mock,
    outage: bool,
) -> None:
    limiter.check.side_effect = RateLimiterUnavailable(TOKEN) if outage else None
    limiter.check.return_value = (False, 17)
    response = registration_client.post(
        PATH, json={"email": EMAIL, "password": PASSWORD}, headers=csrf_headers(registration_client)
    )
    assert response.status_code == (503 if outage else 429)
    assert response.headers["cache-control"] == "no-store" and "set-cookie" not in response.headers
    assert TOKEN not in response.text
    if not outage:
        assert response.headers["retry-after"] == "17"
    registration_service.register.assert_not_called()
    email_sender.send_email_verification.assert_not_called()


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"email": EMAIL, "password": 123},
        {"email": EMAIL, "password": ""},
        {"email": EMAIL, "password": "x" * 1025},
        {"email": EMAIL, "password": PASSWORD, "extra": TOKEN},
        {"email": "x" * 321, "password": PASSWORD},
        "malformed",
    ],
)
def test_registration_transport_validation_is_secret_safe(
    registration_client: TestClient,
    registration_service: Mock,
    email_sender: Mock,
    body: dict[str, object] | str,
) -> None:
    headers = csrf_headers(registration_client)
    if isinstance(body, str):
        response = registration_client.post(
            PATH,
            content='{"password":"' + PASSWORD,
            headers=headers | {"Content-Type": "application/json"},
        )
    else:
        response = registration_client.post(PATH, json=body, headers=headers)
    assert response.status_code == 422 and response.json() == {"detail": "Invalid request."}
    assert (
        "set-cookie" not in response.headers
        and PASSWORD not in response.text
        and TOKEN not in response.text
    )
    registration_service.register.assert_not_called()
    email_sender.send_email_verification.assert_not_called()


@pytest.mark.parametrize("field", ["auth_register_rate_limit", "auth_register_rate_window_seconds"])
def test_registration_rate_settings_are_positive(browser_settings: Settings, field: str) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(browser_settings.model_dump() | {field: 0})


def test_live_registration_login_and_verification(
    live_registration_client: TestClient,
    concurrent_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = cast(FastAPI, live_registration_client.app)
    sender: FakeEmailSender = app.state.email_sender
    original = sender.send_email_verification

    def check_commit(email: str, token: str) -> None:
        with Session(concurrent_engine) as database:
            user = database.scalar(select(UserModel).where(UserModel.email == email))
            assert user and user.email_verified_at is None
            credential = database.get(CredentialModel, user.id)
            session = database.scalar(select(SessionModel).where(SessionModel.user_id == user.id))
            verification = database.scalar(
                select(OneTimeTokenModel).where(OneTimeTokenModel.user_id == user.id)
            )
            assert credential and session and verification
            assert Argon2PasswordHasher().verify(PASSWORD, credential.password_hash)
            assert verification.token_hash == hash_token(token) and verification.used_at is None
            assert (verification.expires_at - verification.created_at).total_seconds() == 86400
            assert app.state.redis.get(f"ukladen:auth:session:{session.token_hash}") is None
        original(email, token)

    monkeypatch.setattr(sender, "send_email_verification", check_commit)
    response = live_registration_client.post(
        PATH,
        json={"email": "  Student@EXAMPLE.COM  ", "password": PASSWORD},
        headers=csrf_headers(live_registration_client),
    )
    assert response.status_code == 201
    session_token = live_registration_client.cookies.get(SESSION_COOKIE)
    assert session_token and session_token not in response.text
    assert len(sender.messages) == 1 and sender.messages[0].email == EMAIL
    verification_token = sender.messages[0].token.get_secret_value()
    assert verification_token not in response.text and verification_token != session_token
    with Session(concurrent_engine) as database:
        session = database.get(SessionModel, UUID(response.json()["session_id"]))
        assert session and session.token_hash == hash_token(session_token)
    assert live_registration_client.get("/api/v1/auth/sessions").status_code == 200
    assert browser_login(live_registration_client) != session_token
    confirmation = live_registration_client.post(
        "/api/v1/auth/email-verification/confirm",
        json={"token": verification_token},
        headers=csrf_headers(live_registration_client),
    )
    assert confirmation.status_code == 204
    with Session(concurrent_engine) as database:
        user = database.get(UserModel, UUID(response.json()["user_id"]))
        token = database.scalar(select(OneTimeTokenModel))
        assert user and user.email_verified_at and token and token.used_at
    assert (
        live_registration_client.post(
            "/api/v1/auth/email-verification/confirm",
            json={"token": verification_token},
            headers=csrf_headers(live_registration_client),
        ).status_code
        == 400
    )


@pytest.mark.parametrize("account", ["password", "google", "disabled"])
def test_live_duplicate_registration_preserves_account(
    live_registration_client: TestClient,
    concurrent_engine: Engine,
    password_hash: str,
    account: str,
) -> None:
    with Session(concurrent_engine) as database, database.begin():
        user = UserModel(email=EMAIL, status="disabled" if account == "disabled" else "active")
        database.add(user)
        database.flush()
        user_id = user.id
        if account == "google":
            database.add(
                IdentityModel(
                    user_id=user_id,
                    provider="google",
                    provider_subject="existing-google-subject",
                    provider_email=EMAIL,
                )
            )
        else:
            database.add(CredentialModel(user_id=user_id, password_hash=password_hash))
    response = live_registration_client.post(
        PATH,
        json={"email": " STUDENT@EXAMPLE.COM ", "password": PASSWORD + "new"},
        headers=csrf_headers(live_registration_client),
    )
    assert response.status_code == 409 and "set-cookie" not in response.headers
    with Session(concurrent_engine) as database:
        users = list(database.scalars(select(UserModel)))
        assert len(users) == 1 and users[0].id == user_id and users[0].email == EMAIL
        assert users[0].status == ("disabled" if account == "disabled" else "active")
        credential = database.get(CredentialModel, user_id)
        assert (
            (credential is None)
            if account == "google"
            else (credential and credential.password_hash == password_hash)
        )
        assert len(list(database.scalars(select(IdentityModel)))) == (
            1 if account == "google" else 0
        )
        assert not list(database.scalars(select(SessionModel)))
        assert not list(database.scalars(select(OneTimeTokenModel)))
    assert not cast(FastAPI, live_registration_client.app).state.email_sender.messages


@pytest.mark.parametrize("failure", ["policy", "email", "late_database"])
def test_live_registration_rejects_or_rolls_back_all_records(
    live_registration_client: TestClient,
    concurrent_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    if failure == "late_database":
        from app.modules.auth.infrastructure.repository import SqlAlchemyRegistrationRepository

        def fail(*args: object) -> None:
            raise SQLAlchemyError(TOKEN)

        monkeypatch.setattr(SqlAlchemyRegistrationRepository, "create_one_time_token", fail)
    response = live_registration_client.post(
        PATH,
        json={
            "email": "Name <student@example.com>" if failure == "email" else EMAIL,
            "password": "short" if failure == "policy" else PASSWORD,
        },
        headers=csrf_headers(live_registration_client),
    )
    assert response.status_code == (503 if failure == "late_database" else 400)
    assert "set-cookie" not in response.headers and TOKEN not in response.text
    with Session(concurrent_engine) as database:
        for model in (UserModel, CredentialModel, SessionModel, OneTimeTokenModel):
            assert not list(database.scalars(select(model)))
    assert not cast(FastAPI, live_registration_client.app).state.email_sender.messages


def test_live_registration_queue_failure_preserves_unverified_account_and_session(
    live_registration_client: TestClient,
    concurrent_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender: FakeEmailSender = cast(FastAPI, live_registration_client.app).state.email_sender

    def fail(*args: object) -> None:
        raise EmailDeliveryUnavailable(TOKEN)

    monkeypatch.setattr(sender, "send_email_verification", fail)
    response = live_registration_client.post(
        PATH,
        json={"email": EMAIL, "password": PASSWORD},
        headers=csrf_headers(live_registration_client),
    )
    assert response.status_code == 201 and live_registration_client.cookies.get(SESSION_COOKIE)
    with Session(concurrent_engine) as database:
        user = database.get(UserModel, UUID(response.json()["user_id"]))
        verification = database.scalar(select(OneTimeTokenModel))
        assert (
            user
            and user.email_verified_at is None
            and verification
            and verification.used_at is None
        )
    assert live_registration_client.get("/api/v1/auth/sessions").status_code == 200
    browser_login(live_registration_client)
    assert not sender.messages


def test_live_registration_redis_rate_window(live_registration_client: TestClient) -> None:
    app = cast(FastAPI, live_registration_client.app)
    app.state.settings = app.state.settings.model_copy(update={"auth_register_rate_limit": 2})
    redis: Redis = app.state.redis
    app.state.rate_limiter = RedisRateLimiter(redis)
    peer = str(IPv6Address(int(IPv6Address("2001:db8::")) | (uuid4().int & ((1 << 96) - 1))))
    key = f"ukladen:auth:rate:register:{hash_token(peer)}"
    client = TestClient(app, base_url=ORIGIN, client=(peer, 50000))
    try:
        headers = csrf_headers(client)
        responses = [
            client.post(
                PATH,
                json={"email": f"student{i}@example.com", "password": PASSWORD},
                headers=headers,
            )
            for i in range(3)
        ]
        assert [response.status_code for response in responses] == [201, 201, 429]
        assert 0 < int(responses[-1].headers["retry-after"]) <= 60
        assert redis.get(key) == b"3"
        assert 0 < cast(int, redis.ttl(key)) <= 60
    finally:
        redis.delete(key)
        client.close()
