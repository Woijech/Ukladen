from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_auth_google_http import (
    CALLBACK,
    IDENTITY,
    ORIGIN,
)
from test_auth_google_http import (
    google_settings as google_settings,
)
from test_auth_google_http import (
    limiter as limiter,
)
from test_auth_google_http import (
    live_client as live_client,
)
from test_auth_google_http import (
    provider as provider,
)
from test_auth_http import browser_login, csrf_headers
from test_auth_login import PASSWORD
from test_auth_login import password_hash as password_hash
from test_auth_sessions import cache as cache
from test_auth_sessions import concurrent_engine as concurrent_engine
from test_auth_sessions import settings as settings

from app.core.config import Settings
from app.modules.auth.application.dto import IssuedSession, OAuthLinkContext
from app.modules.auth.application.google_link import GoogleLinkService
from app.modules.auth.application.service import SessionService
from app.modules.auth.domain.errors import InvalidCredentials, InvalidExternalIdentity
from app.modules.auth.infrastructure.orm import CredentialModel, IdentityModel, SessionModel
from app.modules.auth.infrastructure.password_hasher import Argon2PasswordHasher
from app.modules.auth.infrastructure.repository import (
    SqlAlchemyCredentialRepository,
    SqlAlchemyGoogleIdentityRepository,
    SqlAlchemySessionRepository,
)
from app.modules.auth.infrastructure.token_service import generate_token, hash_token
from app.modules.users.infrastructure.orm import UserModel
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication

PATH = "/api/v1/auth/google/link/start"


def seed(engine: Engine, password_hash: str, email: str = IDENTITY.email):
    user_id = uuid4()
    with Session(engine) as database, database.begin():
        database.add(UserModel(id=user_id, email=email))
        database.flush()
        database.add(CredentialModel(user_id=user_id, password_hash=password_hash))
    return user_id


def start_link(client: TestClient, password: str = PASSWORD) -> str:
    response = client.post(PATH, headers=csrf_headers(client), json={"current_password": password})
    assert response.status_code == 303
    return parse_qs(urlsplit(response.headers["location"]).query)["state"][0]


def service(
    database: Session, cache: Mock, settings: Settings, password_hash: str
) -> GoogleLinkService:
    sessions = SessionService(
        SqlAlchemySessionRepository(database),
        cache,
        settings,
        generate_token=generate_token,
        hash_token=hash_token,
    )
    return GoogleLinkService(
        SqlAlchemyUserAuthentication(database),
        SqlAlchemyCredentialRepository(database),
        Argon2PasswordHasher(),
        SqlAlchemyGoogleIdentityRepository(database),
        sessions,
        hash_token=hash_token,
        dummy_password_hash=password_hash,
    )


def test_live_explicit_link_preserves_password_account_and_supports_google_login(
    live_client: TestClient,
    concurrent_engine: Engine,
    google_settings: Settings,
    password_hash: str,
    provider: Mock,
) -> None:
    user_id = seed(concurrent_engine, password_hash)
    original = browser_login(live_client)
    state = start_link(live_client)
    response = live_client.get(CALLBACK, params={"state": state, "code": "test-code"})
    assert response.headers["location"] == ORIGIN + "/success"
    new_token = live_client.cookies.get(google_settings.auth_session_cookie_name)
    assert new_token and new_token != original
    with Session(concurrent_engine) as database:
        user = database.get(UserModel, user_id)
        credential = database.get(CredentialModel, user_id)
        identity = database.scalar(select(IdentityModel))
        assert user and user.email == IDENTITY.email and user.email_verified_at is None
        assert credential and credential.password_hash == password_hash
        assert (
            identity
            and identity.user_id == user_id
            and identity.provider_subject == IDENTITY.subject
        )
        assert database.scalar(select(func.count()).select_from(UserModel)) == 1
        assert database.scalar(select(func.count()).select_from(SessionModel)) == 2
    assert (
        live_client.get(CALLBACK, params={"state": state, "code": "test-code"}).headers["location"]
        == ORIGIN + "/error"
    )
    assert provider.resolve_callback.call_count == 1
    assert browser_login(live_client)  # Existing password remains usable.
    response = live_client.get("/api/v1/auth/google/start")
    state = parse_qs(urlsplit(response.headers["location"]).query)["state"][0]
    assert (
        live_client.get(CALLBACK, params={"state": state, "code": "test-code"}).headers["location"]
        == ORIGIN + "/success"
    )
    with Session(concurrent_engine) as database:
        assert database.scalar(select(func.count()).select_from(UserModel)) == 1
        assert database.scalar(select(func.count()).select_from(IdentityModel)) == 1


@pytest.mark.parametrize(
    "failure",
    [
        "logout",
        "session-switch",
        "password-change",
        "disabled",
        "other-owner",
        "revoked",
        "expired",
    ],
)
def test_live_callback_rechecks_reauthentication_and_original_session(
    live_client: TestClient,
    concurrent_engine: Engine,
    google_settings: Settings,
    password_hash: str,
    failure: str,
) -> None:
    user_id = seed(concurrent_engine, password_hash)
    token = browser_login(live_client)
    state = start_link(live_client)
    if failure == "logout":
        live_client.cookies.delete(google_settings.auth_session_cookie_name)
    elif failure == "session-switch":
        token = browser_login(live_client)
    else:
        with Session(concurrent_engine) as database, database.begin():
            if failure == "password-change":
                database.execute(
                    update(CredentialModel)
                    .where(CredentialModel.user_id == user_id)
                    .values(password_hash="changed-credential")
                )
            elif failure == "disabled":
                database.execute(
                    update(UserModel).where(UserModel.id == user_id).values(status="disabled")
                )
            elif failure == "other-owner":
                other = UserModel(email="other@example.com")
                database.add(other)
                database.flush()
                SqlAlchemyGoogleIdentityRepository(database).create(
                    other.id, IDENTITY.subject, IDENTITY.email, datetime.now(UTC)
                )
            elif failure == "revoked":
                database.execute(
                    update(SessionModel)
                    .where(SessionModel.token_hash == hash_token(token))
                    .values(revoked_at=datetime.now(UTC))
                )
            elif failure == "expired":
                now = datetime.now(UTC)
                database.execute(
                    update(SessionModel)
                    .where(SessionModel.token_hash == hash_token(token))
                    .values(
                        created_at=now - timedelta(days=1), expires_at=now - timedelta(seconds=1)
                    )
                )
    response = live_client.get(CALLBACK, params={"state": state, "code": "test-code"})
    assert (
        response.headers["location"] == ORIGIN + "/error" and "set-cookie" not in response.headers
    )
    assert live_client.cookies.get(google_settings.auth_session_cookie_name) == (
        None if failure == "logout" else token
    )
    with Session(concurrent_engine) as database:
        assert database.scalar(select(func.count()).select_from(IdentityModel)) == (
            failure == "other-owner"
        )
        assert database.scalar(select(func.count()).select_from(SessionModel)) == (
            2 if failure == "session-switch" else 1
        )
        if failure == "other-owner":
            identity = database.scalar(select(IdentityModel))
            assert identity and identity.user_id != user_id


@pytest.mark.parametrize("case", ["password", "csrf", "extra", "rate", "strict-cookie"])
def test_live_initiation_requires_password_csrf_and_rate_limit(
    live_client: TestClient,
    concurrent_engine: Engine,
    password_hash: str,
    provider: Mock,
    limiter: Mock,
    case: str,
) -> None:
    user_id = seed(concurrent_engine, password_hash)
    browser_login(live_client)
    headers = csrf_headers(live_client) if case != "csrf" else {}
    body = {"current_password": "wrong-password" if case == "password" else PASSWORD}
    if case == "extra":
        body["user_id"] = str(uuid4())
    elif case == "rate":
        limiter.check.return_value = (False, 10)
    elif case == "strict-cookie":
        assert isinstance(live_client.app, FastAPI)
        live_client.app.state.settings.auth_cookie_samesite = "strict"
    response = live_client.post(PATH, headers=headers, json=body)
    assert (
        response.status_code
        == {"password": 401, "csrf": 403, "extra": 422, "rate": 429, "strict-cookie": 503}[case]
    )
    assert "set-cookie" not in response.headers and PASSWORD not in response.text
    provider.build_authorization_url.assert_not_called()
    with Session(concurrent_engine) as database:
        assert database.scalar(select(func.count()).select_from(IdentityModel)) == 0
    if case == "rate":
        assert limiter.check.call_args.args == (f"google-link:{user_id}", 5, 60)


def test_live_google_only_account_cannot_link_with_a_password(
    live_client: TestClient,
    concurrent_engine: Engine,
    provider: Mock,
) -> None:
    response = live_client.get("/api/v1/auth/google/start")
    state = parse_qs(urlsplit(response.headers["location"]).query)["state"][0]
    assert (
        live_client.get(CALLBACK, params={"state": state, "code": "test-code"}).headers["location"]
        == ORIGIN + "/success"
    )
    provider.build_authorization_url.reset_mock()
    response = live_client.post(
        PATH, headers=csrf_headers(live_client), json={"current_password": PASSWORD}
    )
    assert response.status_code == 401
    provider.build_authorization_url.assert_not_called()


def test_live_link_rollback_never_leaves_identity_and_fresh_retry_works(
    live_client: TestClient,
    concurrent_engine: Engine,
    google_settings: Settings,
    password_hash: str,
) -> None:
    seed(concurrent_engine, password_hash)
    token = browser_login(live_client)
    state = start_link(live_client)
    original = SqlAlchemySessionRepository.create

    def fail_after_insert(repository: SqlAlchemySessionRepository, session) -> None:
        original(repository, session)
        raise SQLAlchemyError("injected insertion failure")

    with patch.object(SqlAlchemySessionRepository, "create", fail_after_insert):
        assert (
            live_client.get(CALLBACK, params={"state": state, "code": "test-code"}).headers[
                "location"
            ]
            == ORIGIN + "/error"
        )
    assert live_client.cookies.get(google_settings.auth_session_cookie_name) == token
    with Session(concurrent_engine) as database:
        assert database.scalar(select(func.count()).select_from(IdentityModel)) == 0
        assert database.scalar(select(func.count()).select_from(SessionModel)) == 1
    state = start_link(live_client)
    assert (
        live_client.get(CALLBACK, params={"state": state, "code": "test-code"}).headers["location"]
        == ORIGIN + "/success"
    )


def test_live_competing_users_never_reassign_google_subject(
    concurrent_engine: Engine,
    settings: Settings,
    password_hash: str,
    cache: Mock,
) -> None:
    contexts: list[tuple[OAuthLinkContext, str]] = []
    for email in ("one@example.com", "two@example.com"):
        user_id = seed(concurrent_engine, password_hash, email)
        with Session(concurrent_engine) as database, database.begin():
            links = service(database, cache, settings, password_hash)
            issued = links.sessions.create(user_id)
            contexts.append((links.prepare(issued.session, PASSWORD), issued.token))
    barrier = Barrier(2)

    def attempt(context: OAuthLinkContext, token: str) -> IssuedSession | None:
        with Session(concurrent_engine) as database:
            links = service(database, cache, settings, password_hash)
            lookup = links.identities.get_user_id

            def synchronized_lookup(subject: str):
                result = lookup(subject)
                assert result is None
                barrier.wait(timeout=5)
                return result

            with patch.object(links.identities, "get_user_id", side_effect=synchronized_lookup):
                try:
                    with database.begin():
                        return links.complete(IDENTITY, context, token)
                except InvalidExternalIdentity:
                    return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(attempt, *context) for context in contexts]
        results = [future.result(timeout=10) for future in futures]
    winners = [result for result in results if result is not None]
    assert len(winners) == 1
    with Session(concurrent_engine) as database:
        identity = database.scalar(select(IdentityModel))
        assert identity and identity.user_id == winners[0].session.user_id
        assert database.scalar(select(func.count()).select_from(UserModel)) == 2
        assert database.scalar(select(func.count()).select_from(SessionModel)) == 3


def test_live_link_prepare_rejects_out_of_policy_password_before_db(
    concurrent_engine: Engine,
    settings: Settings,
    password_hash: str,
    cache: Mock,
) -> None:
    user_id = seed(concurrent_engine, password_hash)
    with Session(concurrent_engine) as database, database.begin():
        links = service(database, cache, settings, password_hash)
        issued = links.sessions.create(user_id)
        with patch.object(links.users, "lock_active") as lock:
            with pytest.raises(InvalidCredentials):
                links.prepare(issued.session, "x" * 1025)
            lock.assert_not_called()
