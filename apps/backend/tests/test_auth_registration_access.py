import re
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session
from test_auth_google_http import google_settings as google_settings
from test_auth_google_http import limiter as limiter
from test_auth_google_http import live_client as live_client
from test_auth_google_http import provider as provider
from test_auth_http import csrf_headers
from test_auth_login import PASSWORD
from test_auth_login import password_hash as password_hash
from test_auth_sessions import concurrent_engine as concurrent_engine
from test_auth_sessions import settings as settings

from app.core.config import Settings
from app.modules.auth.infrastructure.email_sender import FakeEmailSender
from app.modules.auth.infrastructure.orm import CredentialModel, IdentityModel, SessionModel
from app.modules.auth.infrastructure.password_hasher import Argon2PasswordHasher
from app.modules.auth.infrastructure.token_service import generate_token, hash_token
from app.modules.auth.presentation.dependencies import get_email_sender
from app.modules.users.infrastructure.orm import UserModel


def seed(
    client: TestClient, engine: Engine, config: Settings, password: str | None, verified: bool
):
    now = datetime.now(UTC)
    user_id, session_id, token = uuid4(), uuid4(), generate_token()
    with Session(engine) as database, database.begin():
        database.add(
            UserModel(
                id=user_id, email="student@example.com", email_verified_at=now if verified else None
            )
        )
        database.flush()
        if password is not None:
            database.add(CredentialModel(user_id=user_id, password_hash=password))
        database.add(
            SessionModel(
                id=session_id,
                user_id=user_id,
                token_hash=hash_token(token),
                created_at=now,
                last_seen_at=now,
                expires_at=now + timedelta(days=1),
            )
        )
    client.cookies.set(config.auth_session_cookie_name, token)
    return user_id


@pytest.mark.parametrize(
    "verified,password_present", [(False, True), (True, False), (False, False), (True, True)]
)
def test_canonical_registration_state_controls_access(
    live_client: TestClient,
    concurrent_engine: Engine,
    google_settings: Settings,
    password_hash: str,
    verified: bool,
    password_present: bool,
) -> None:
    seed(
        live_client,
        concurrent_engine,
        google_settings,
        password_hash if password_present else None,
        verified,
    )
    response = live_client.get("/api/v1/auth/registration")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "email": "student@example.com",
        "email_verified": verified,
        "password_required": not password_present,
        "complete": verified and password_present,
        "password_min_length": google_settings.auth_password_min_length,
    }
    response = live_client.get("/api/v1/users/me")
    assert response.status_code == (200 if verified and password_present else 403)
    if not (verified and password_present):
        assert response.json()["code"] == "registration_incomplete"
        assert "set-cookie" not in response.headers


def test_pending_registration_cannot_read_any_business_module(
    live_client: TestClient,
    concurrent_engine: Engine,
    google_settings: Settings,
    password_hash: str,
) -> None:
    seed(live_client, concurrent_engine, google_settings, password_hash, False)
    paths = live_client.get("/api/openapi.json").json()["paths"]
    checked = set()
    for path, methods in paths.items():
        if (
            not path.startswith("/api/v1/")
            or path.startswith("/api/v1/auth/")
            or "get" not in methods
        ):
            continue
        url = re.sub(r"\{[^}]+\}", str(uuid4()), path)
        response = live_client.get(url)
        assert response.status_code == 403, (path, response.status_code)
        assert response.json()["code"] == "registration_incomplete"
        checked.add(path.split("/")[3])
    assert {"users", "academics", "calendar", "materials", "notes", "search"} <= checked


def test_cached_session_cannot_bypass_canonical_verification(
    live_client: TestClient,
    concurrent_engine: Engine,
    google_settings: Settings,
    password_hash: str,
) -> None:
    user_id = seed(live_client, concurrent_engine, google_settings, password_hash, True)
    assert live_client.get("/api/v1/users/me").status_code == 200
    with Session(concurrent_engine) as database, database.begin():
        database.execute(
            update(UserModel).where(UserModel.id == user_id).values(email_verified_at=None)
        )
    assert live_client.get("/api/v1/users/me").status_code == 403
    assert live_client.get("/api/v1/auth/registration").json()["email_verified"] is False


def test_password_setup_preserves_verification_and_never_overwrites_a_password(
    live_client: TestClient,
    concurrent_engine: Engine,
    google_settings: Settings,
) -> None:
    user_id = seed(live_client, concurrent_engine, google_settings, None, True)
    headers = csrf_headers(live_client)
    response = live_client.post(
        "/api/v1/auth/registration/password", headers=headers, json={"password": PASSWORD}
    )
    assert response.status_code == 204
    assert PASSWORD not in response.text and "set-cookie" not in response.headers
    with Session(concurrent_engine) as database:
        credential = database.scalar(
            select(CredentialModel).where(CredentialModel.user_id == user_id)
        )
        assert credential and Argon2PasswordHasher().verify(PASSWORD, credential.password_hash)
    assert live_client.get("/api/v1/users/me").status_code == 200
    assert (
        live_client.post(
            "/api/v1/auth/registration/password",
            headers=headers,
            json={"password": "another-password-long"},
        ).status_code
        == 409
    )


@pytest.mark.parametrize("case", ["csrf", "short", "extra", "rate"])
def test_invalid_password_setup_cannot_create_credentials(
    live_client: TestClient,
    concurrent_engine: Engine,
    google_settings: Settings,
    limiter: Mock,
    case: str,
) -> None:
    user_id = seed(live_client, concurrent_engine, google_settings, None, True)
    headers = csrf_headers(live_client) if case != "csrf" else {}
    if case == "rate":
        limiter.check.return_value = (False, 12)
    body = {"password": "short" if case == "short" else PASSWORD}
    if case == "extra":
        body["user_id"] = str(uuid4())
    response = live_client.post("/api/v1/auth/registration/password", headers=headers, json=body)
    assert response.status_code == {"csrf": 403, "short": 400, "extra": 422, "rate": 429}[case]
    with Session(concurrent_engine) as database:
        assert database.get(CredentialModel, user_id) is None


def test_pending_session_can_request_verification_and_log_out(
    live_client: TestClient,
    concurrent_engine: Engine,
    google_settings: Settings,
    password_hash: str,
) -> None:
    seed(live_client, concurrent_engine, google_settings, password_hash, False)
    sender = Mock()
    cast(FastAPI, live_client.app).dependency_overrides[get_email_sender] = lambda: sender
    headers = csrf_headers(live_client)
    response = live_client.post("/api/v1/auth/email-verification/request", headers=headers, json={})
    assert response.status_code == 202
    assert sender.send_email_verification.call_args.args[0] == "student@example.com"
    assert live_client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert live_client.get("/api/v1/auth/registration").status_code == 401


@pytest.mark.parametrize("password_present", [False, True])
def test_mailbox_recovery_completes_pending_signup_and_removes_prior_access(
    live_client: TestClient,
    concurrent_engine: Engine,
    google_settings: Settings,
    password_hash: str,
    password_present: bool,
) -> None:
    user_id = seed(
        live_client,
        concurrent_engine,
        google_settings,
        password_hash if password_present else None,
        False,
    )
    previous_token = live_client.cookies.get(google_settings.auth_session_cookie_name)
    assert live_client.get("/api/v1/auth/registration").status_code == 200
    with Session(concurrent_engine) as database, database.begin():
        database.add(
            IdentityModel(
                user_id=user_id,
                provider="google",
                provider_subject="prior-identity",
                provider_email="prior@example.com",
            )
        )
    sender = FakeEmailSender()
    cast(FastAPI, live_client.app).dependency_overrides[get_email_sender] = lambda: sender
    assert (
        live_client.post(
            "/api/v1/auth/password-reset/request",
            headers=csrf_headers(live_client),
            json={"email": "student@example.com"},
        ).status_code
        == 202
    )
    token = sender.messages[-1].token.get_secret_value()
    new_password = "new-password-after-recovery"
    assert (
        live_client.post(
            "/api/v1/auth/password-reset/confirm",
            headers=csrf_headers(live_client),
            json={"token": token, "new_password": new_password},
        ).status_code
        == 204
    )
    with Session(concurrent_engine) as database:
        credential = database.get(CredentialModel, user_id)
        user = database.get(UserModel, user_id)
        assert credential and Argon2PasswordHasher().verify(new_password, credential.password_hash)
        assert user and user.email_verified_at is not None
        assert (
            database.scalar(select(IdentityModel).where(IdentityModel.user_id == user_id)) is None
        )
        assert all(row.revoked_at is not None for row in database.scalars(select(SessionModel)))
    assert previous_token
    live_client.cookies.set(google_settings.auth_session_cookie_name, previous_token)
    assert live_client.get("/api/v1/auth/registration").status_code == 401
    assert (
        live_client.post(
            "/api/v1/auth/login",
            headers=csrf_headers(live_client),
            json={"email": "student@example.com", "password": new_password},
        ).status_code
        == 200
    )
    assert live_client.get("/api/v1/users/me").status_code == 200
