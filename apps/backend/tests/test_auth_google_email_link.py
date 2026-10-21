from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session
from test_auth_google_http import CALLBACK, ORIGIN
from test_auth_google_http import google_settings as google_settings
from test_auth_google_http import limiter as limiter
from test_auth_google_http import live_client as live_client
from test_auth_google_http import provider as provider
from test_auth_http import csrf_headers
from test_auth_login import password_hash as password_hash
from test_auth_registration_access import seed
from test_auth_sessions import concurrent_engine as concurrent_engine
from test_auth_sessions import settings as settings

from app.core.config import Settings
from app.modules.auth.application.dto import VerifiedGoogleIdentity
from app.modules.auth.infrastructure.email_sender import EmailKind, FakeEmailSender
from app.modules.auth.infrastructure.orm import (
    CredentialModel,
    GoogleEmailConfirmationModel,
    IdentityModel,
)
from app.modules.auth.presentation.dependencies import get_callback_email_sender
from app.modules.users.infrastructure.orm import UserModel

CONFIRM = "/api/v1/auth/google/email/confirm"


def begin(client: TestClient, provider: Mock):
    sender = FakeEmailSender()
    cast(FastAPI, client.app).dependency_overrides[get_callback_email_sender] = lambda: sender
    provider.resolve_callback.return_value = VerifiedGoogleIdentity(
        "external-subject", "student@example.com"
    )
    response = client.get("/api/v1/auth/google/start")
    state = parse_qs(urlsplit(response.headers["location"]).query)["state"][0]
    response = client.get(CALLBACK, params={"state": state, "code": "private-code"})
    assert response.status_code == 303
    assert (
        response.headers["location"] == ORIGIN + "/error?reason=google_email_confirmation_required"
    )
    assert response.headers["cache-control"] == "no-store"
    assert sender.messages[-1].kind == EmailKind.GOOGLE_LINK
    return sender.messages[-1].token.get_secret_value()


def test_third_party_google_link_requires_browser_bound_single_use_email_proof(
    live_client: TestClient,
    concurrent_engine: Engine,
    google_settings: Settings,
    password_hash: str,
    provider: Mock,
) -> None:
    user_id = seed(live_client, concurrent_engine, google_settings, password_hash, True)
    live_client.cookies.clear()
    token = begin(live_client, provider)
    assert not live_client.cookies.get(google_settings.auth_session_cookie_name)
    with Session(concurrent_engine) as database:
        assert database.scalar(select(func.count()).select_from(IdentityModel)) == 0
        record = database.scalar(select(GoogleEmailConfirmationModel))
        assert record and record.token_hash != token and record.used_at is None
    response = live_client.post(CONFIRM, headers=csrf_headers(live_client), json={"token": token})
    assert response.status_code == 204
    assert (
        token not in response.text
        and live_client.cookies.get(google_settings.auth_oauth_cookie_name) is None
    )
    assert live_client.get("/api/v1/users/me").json()["id"] == str(user_id)
    with Session(concurrent_engine) as database:
        credential = database.get(CredentialModel, user_id)
        assert credential and credential.password_hash == password_hash
        identity = database.scalar(select(IdentityModel))
        assert (
            identity
            and identity.user_id == user_id
            and identity.provider_subject == "external-subject"
        )
    assert (
        live_client.post(
            CONFIRM, headers=csrf_headers(live_client), json={"token": token}
        ).status_code
        == 400
    )


@pytest.mark.parametrize(
    "failure", ["wrong-browser", "expired", "password-change", "disabled", "other-owner", "csrf"]
)
def test_failed_google_email_proof_cannot_attach_an_identity(
    live_client: TestClient,
    concurrent_engine: Engine,
    google_settings: Settings,
    password_hash: str,
    provider: Mock,
    failure: str,
) -> None:
    user_id = seed(live_client, concurrent_engine, google_settings, password_hash, True)
    live_client.cookies.clear()
    token = begin(live_client, provider)
    original_browser = live_client.cookies.get(google_settings.auth_oauth_cookie_name)
    assert original_browser is not None
    if failure == "wrong-browser":
        live_client.cookies.delete(google_settings.auth_oauth_cookie_name)
    with Session(concurrent_engine) as database, database.begin():
        if failure == "expired":
            now = datetime.now(UTC)
            database.execute(
                update(GoogleEmailConfirmationModel).values(
                    created_at=now - timedelta(hours=1), expires_at=now - timedelta(seconds=1)
                )
            )
        elif failure == "password-change":
            database.execute(update(CredentialModel).values(password_hash="changed"))
        elif failure == "disabled":
            database.execute(
                update(UserModel).where(UserModel.id == user_id).values(status="disabled")
            )
        elif failure == "other-owner":
            other = UserModel(id=uuid4(), email="other@example.com")
            database.add(other)
            database.flush()
            database.add(
                IdentityModel(
                    user_id=other.id,
                    provider="google",
                    provider_subject="external-subject",
                    provider_email="student@example.com",
                )
            )
    headers = {} if failure == "csrf" else csrf_headers(live_client)
    response = live_client.post(CONFIRM, headers=headers, json={"token": token})
    assert response.status_code == (403 if failure == "csrf" else 400)
    assert token not in response.text and "set-cookie" not in response.headers
    with Session(concurrent_engine) as database:
        record = database.scalar(select(GoogleEmailConfirmationModel))
        assert record and record.used_at is None
        assert (
            database.scalar(
                select(func.count())
                .select_from(IdentityModel)
                .where(IdentityModel.user_id == user_id)
            )
            == 0
        )
    if failure == "wrong-browser":
        live_client.cookies.set(google_settings.auth_oauth_cookie_name, original_browser)
        assert (
            live_client.post(
                CONFIRM, headers=csrf_headers(live_client), json={"token": token}
            ).status_code
            == 204
        )


def test_unverified_legacy_account_is_not_claimed_by_a_google_email_match(
    live_client: TestClient,
    concurrent_engine: Engine,
    google_settings: Settings,
    password_hash: str,
    provider: Mock,
) -> None:
    seed(live_client, concurrent_engine, google_settings, password_hash, False)
    live_client.cookies.clear()
    provider.resolve_callback.return_value = VerifiedGoogleIdentity(
        "external-subject", "student@example.com"
    )
    response = live_client.get("/api/v1/auth/google/start")
    state = parse_qs(urlsplit(response.headers["location"]).query)["state"][0]
    response = live_client.get(CALLBACK, params={"state": state, "code": "private-code"})
    assert response.headers["location"] == ORIGIN + "/error?reason=account_linking_required"
    with Session(concurrent_engine) as database:
        assert database.scalar(select(func.count()).select_from(GoogleEmailConfirmationModel)) == 0
        assert database.scalar(select(func.count()).select_from(IdentityModel)) == 0
