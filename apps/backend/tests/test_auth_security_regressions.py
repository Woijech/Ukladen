from ipaddress import IPv6Address
from typing import cast
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from test_auth_http import ORIGIN, PASSWORD, browser_login, csrf_headers, seed_user
from test_auth_http import browser_settings as browser_settings
from test_auth_http import live_client as live_client
from test_auth_login import password_hash as password_hash
from test_auth_registration_http import live_registration_client as live_registration_client
from test_auth_sessions import concurrent_engine as concurrent_engine
from test_auth_sessions import settings as settings

from app.modules.auth.infrastructure.email_sender import FakeEmailSender
from app.modules.auth.infrastructure.orm import OneTimeTokenModel
from app.modules.auth.infrastructure.request_protection import RedisRateLimiter
from app.modules.auth.infrastructure.token_service import hash_token
from app.modules.users.infrastructure.orm import UserModel


def mail_token(client: TestClient) -> str:
    sender = cast(FakeEmailSender, cast(FastAPI, client.app).state.email_sender)
    return sender.messages[-1].token.get_secret_value()


@pytest.mark.parametrize("email", ["student@outlook.com", "student@yandex.ru", "student@proton.me"])
def test_non_google_mail_registration_confirmation_and_password_login(
    live_registration_client: TestClient, email: str
) -> None:
    client = live_registration_client
    assert (
        client.post(
            "/api/v1/auth/register",
            headers=csrf_headers(client),
            json={"email": email, "password": PASSWORD},
        ).status_code
        == 201
    )
    assert client.get("/api/v1/users/me").status_code == 403
    assert (
        client.post(
            "/api/v1/auth/email-verification/confirm",
            headers=csrf_headers(client),
            json={"token": mail_token(client)},
        ).status_code
        == 204
    )
    assert client.get("/api/v1/users/me").json()["email"] == email
    assert client.post("/api/v1/auth/logout", headers=csrf_headers(client)).status_code == 204
    browser_login(client, email)
    assert client.get("/api/v1/users/me").json()["email"] == email


@pytest.mark.parametrize("other_account", [False, True])
def test_mail_link_in_another_browser_cannot_activate_an_attacker_registration(
    live_registration_client: TestClient,
    concurrent_engine: Engine,
    password_hash: str,
    other_account: bool,
) -> None:
    attacker = live_registration_client
    assert (
        attacker.post(
            "/api/v1/auth/register",
            headers=csrf_headers(attacker),
            json={"email": "owner@example.com", "password": PASSWORD},
        ).status_code
        == 201
    )
    token = mail_token(attacker)
    owner = TestClient(attacker.app, base_url=ORIGIN)
    try:
        if other_account:
            seed_user(concurrent_engine, "another@example.com", password_hash)
            browser_login(owner, "another@example.com")
        response = owner.post(
            "/api/v1/auth/email-verification/confirm",
            headers=csrf_headers(owner),
            json={"token": token},
        )
        assert response.status_code == (400 if other_account else 401)
        assert attacker.get("/api/v1/users/me").status_code == 403
        with Session(concurrent_engine) as database:
            user = database.scalar(select(UserModel).where(UserModel.email == "owner@example.com"))
            assert user and user.email_verified_at is None
            proof = database.scalar(
                select(OneTimeTokenModel).where(OneTimeTokenModel.token_hash == hash_token(token))
            )
            assert proof and proof.used_at is None
    finally:
        owner.close()


@pytest.mark.parametrize("change", ["reset", "password_change"])
def test_password_change_invalidates_all_earlier_reset_links(
    live_registration_client: TestClient,
    concurrent_engine: Engine,
    password_hash: str,
    change: str,
) -> None:
    client = live_registration_client
    email = "student@example.com"
    seed_user(concurrent_engine, email, password_hash)
    tokens = []
    for _ in range(2):
        assert (
            client.post(
                "/api/v1/auth/password-reset/request",
                headers=csrf_headers(client),
                json={"email": email},
            ).status_code
            == 202
        )
        tokens.append(mail_token(client))
    if change == "reset":
        response = client.post(
            "/api/v1/auth/password-reset/confirm",
            headers=csrf_headers(client),
            json={"token": tokens[0], "new_password": "owner-new-password"},
        )
    else:
        browser_login(client)
        response = client.post(
            "/api/v1/auth/password/change",
            headers=csrf_headers(client),
            json={"current_password": PASSWORD, "new_password": "owner-new-password"},
        )
    assert response.status_code == 204
    assert (
        client.post(
            "/api/v1/auth/password-reset/confirm",
            headers=csrf_headers(client),
            json={"token": tokens[-1], "new_password": "stale-link-password"},
        ).status_code
        == 400
    )


@pytest.mark.parametrize("operation", ["login", "password-reset/request"])
def test_account_attempts_are_limited_across_different_client_addresses(
    live_registration_client: TestClient,
    concurrent_engine: Engine,
    password_hash: str,
    operation: str,
) -> None:
    email = f"{uuid4().hex}@example.com"
    seed_user(concurrent_engine, email, password_hash)
    app = cast(FastAPI, live_registration_client.app)
    app.state.settings = app.state.settings.model_copy(
        update={
            "auth_login_rate_limit": 2,
            "auth_password_reset_request_rate_limit": 2,
        }
    )
    app.state.rate_limiter = RedisRateLimiter(app.state.redis)
    prefix = "login" if operation == "login" else "password-reset-request"
    email_prefix = "login-email" if operation == "login" else "password-reset-email"
    keys = [f"ukladen:auth:rate:{email_prefix}:{hash_token(email)}"]
    try:
        for index, expected in enumerate(
            (401, 401, 429) if operation == "login" else (202, 202, 429)
        ):
            peer = str(IPv6Address(uuid4().int))
            keys.append(f"ukladen:auth:rate:{prefix}:{hash_token(peer)}")
            client = TestClient(app, base_url=ORIGIN, client=(peer, 50000))
            try:
                payload = {"email": f" {email.upper()} " if index else email}
                if operation == "login":
                    payload["password"] = "wrong-password"
                response = client.post(
                    f"/api/v1/auth/{operation}", headers=csrf_headers(client), json=payload
                )
                assert response.status_code == expected
            finally:
                client.close()
    finally:
        app.state.redis.delete(*keys)
