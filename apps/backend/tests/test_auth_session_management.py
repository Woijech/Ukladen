from dataclasses import replace
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from typing import cast
from unittest.mock import Mock, create_autospec
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
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
from test_auth_sessions import NOW, service

from app.core.config import Settings
from app.modules.auth.application.dto import IssuedSession
from app.modules.auth.application.ports import (
    SessionCache,
    SessionCacheUnavailable,
    SessionRepository,
)
from app.modules.auth.domain.errors import SessionNotFound
from app.modules.auth.infrastructure.orm import SessionModel
from app.modules.auth.infrastructure.repository import SqlAlchemySessionRepository
from app.modules.auth.infrastructure.token_service import generate_token, hash_token
from app.modules.auth.presentation.dependencies import get_current_session
from app.modules.users.infrastructure.orm import UserModel


def test_session_service_uses_owner_and_clock(settings: Settings) -> None:
    repository = create_autospec(SessionRepository, instance=True)
    cache = create_autospec(SessionCache, instance=True)
    sessions = service(repository, cache, settings)
    user_id, session_id = uuid4(), uuid4()
    repository.list_active_for_user.return_value = []
    assert sessions.list_active_for_user(user_id) == []
    repository.list_active_for_user.assert_called_once_with(user_id, NOW)
    repository.revoke_for_user.return_value = None
    with pytest.raises(SessionNotFound):
        sessions.revoke_for_user(session_id, user_id)
    cache.delete.assert_not_called()
    repository.revoke_for_user.return_value = "a" * 64
    sessions.revoke_for_user(session_id, user_id)
    repository.revoke_for_user.assert_called_with(session_id, user_id)
    cache.delete.assert_called_once_with("a" * 64)
    cache.delete.side_effect = SessionCacheUnavailable("Session cache is unavailable.")
    with pytest.raises(SessionCacheUnavailable):
        sessions.revoke_for_user(session_id, user_id)


def test_listing_returns_only_public_metadata(
    client: TestClient, sessions: Mock, issued: IssuedSession
) -> None:
    current = replace(
        issued.session, user_agent="Test browser", ip_address=ip_address("2001:db8::1")
    )
    other = replace(current, id=uuid4())
    sessions.list_active_for_user.return_value = [current, other]
    response = client.get("/api/v1/auth/sessions")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert [item["is_current"] for item in response.json()] == [True, False]
    assert set(response.json()[0]) == {
        "id",
        "created_at",
        "last_seen_at",
        "expires_at",
        "user_agent",
        "ip_address",
        "is_current",
    }
    assert response.json()[0]["ip_address"] == "2001:db8::1"
    assert response.json()[0]["user_agent"] == "Test browser"
    assert issued.token not in response.text and current.token_hash not in response.text
    sessions.list_active_for_user.assert_called_once_with(current.user_id)


@pytest.mark.parametrize("outcome", ["current", "other", "missing", "cache", "commit"])
def test_revoke_cookie_and_errors_follow_transaction(
    client: TestClient, sessions: Mock, database: Mock, issued: IssuedSession, outcome: str
) -> None:
    session_id = uuid4() if outcome == "other" else issued.session.id
    if outcome == "missing":
        sessions.revoke_for_user.side_effect = SessionNotFound("private details")
    elif outcome == "cache":
        sessions.revoke_for_user.side_effect = SessionCacheUnavailable("private details")
    elif outcome == "commit":
        database.begin.return_value.__exit__.side_effect = SQLAlchemyError("private details")
    response = client.delete(f"/api/v1/auth/sessions/{session_id}", headers=csrf_headers(client))
    sessions.revoke_for_user.assert_called_once_with(session_id, issued.session.user_id)
    assert response.headers["cache-control"] == "no-store" and "private" not in response.text
    expected = 404 if outcome == "missing" else 503 if outcome in ("cache", "commit") else 204
    assert response.status_code == expected
    if outcome == "current":
        assert "Max-Age=0" in response.headers["set-cookie"]
    else:
        assert "set-cookie" not in response.headers
    if expected == 204:
        assert response.content == b""


@pytest.mark.parametrize("missing", ["Origin", "X-CSRF-Token"])
def test_revoke_requires_csrf(client: TestClient, sessions: Mock, missing: str) -> None:
    headers = csrf_headers(client)
    headers.pop(missing)
    response = client.delete(f"/api/v1/auth/sessions/{uuid4()}", headers=headers)
    assert response.status_code == 403
    sessions.revoke_for_user.assert_not_called()


def test_revoke_validates_uuid(client: TestClient, sessions: Mock) -> None:
    response = client.delete("/api/v1/auth/sessions/not-a-uuid", headers=csrf_headers(client))
    assert response.status_code == 422 and response.json() == {"detail": "Invalid request."}
    sessions.revoke_for_user.assert_not_called()


@pytest.mark.parametrize("method", ["get", "delete"])
def test_session_management_requires_authentication(
    client: TestClient, application: FastAPI, sessions: Mock, method: str
) -> None:
    application.dependency_overrides.pop(get_current_session)
    path = "/api/v1/auth/sessions" + (f"/{uuid4()}" if method == "delete" else "")
    response = client.request(method, path, headers=csrf_headers(client))
    assert response.status_code == 401
    sessions.list_active_for_user.assert_not_called()
    sessions.revoke_for_user.assert_not_called()


def test_live_listing_and_owned_revocation(
    live_client: TestClient, concurrent_engine: Engine, password_hash: str
) -> None:
    seed_user(concurrent_engine, "student@example.com", password_hash)
    seed_user(concurrent_engine, "other@example.com", password_hash)
    foreign = browser_login(live_client, "other@example.com")
    first = browser_login(live_client)
    # Validate the first cookie so revocation must also remove its cached session.
    assert live_client.get("/api/v1/auth/sessions").status_code == 200
    second = browser_login(live_client)
    now = datetime.now(UTC)
    with Session(concurrent_engine) as database, database.begin():
        first_row = database.scalar(
            select(SessionModel).where(SessionModel.token_hash == hash_token(first))
        )
        foreign_row = database.scalar(
            select(SessionModel).where(SessionModel.token_hash == hash_token(foreign))
        )
        assert first_row and foreign_row
        first_id, foreign_id, user_id = first_row.id, foreign_row.id, first_row.user_id
        for state in ("expired", "revoked", "future"):
            created = now + timedelta(days=1) if state == "future" else now - timedelta(days=3)
            expiry = now - timedelta(days=1) if state == "expired" else now + timedelta(days=2)
            database.add(
                SessionModel(
                    user_id=user_id,
                    token_hash=hash_token(generate_token()),
                    created_at=created,
                    last_seen_at=created,
                    expires_at=expiry,
                    revoked_at=now if state == "revoked" else None,
                )
            )
    response = live_client.get("/api/v1/auth/sessions")
    assert response.status_code == 200
    listed = response.json()
    assert len(listed) == 2 and listed[0]["is_current"] and not listed[1]["is_current"]
    assert listed[1]["id"] == str(first_id)
    second_id = UUID(listed[0]["id"])
    client_redis: Redis = cast(FastAPI, live_client.app).state.redis
    first_key = f"ukladen:auth:session:{hash_token(first)}"
    assert client_redis.exists(first_key)
    foreign_response = live_client.delete(
        f"/api/v1/auth/sessions/{foreign_id}", headers=csrf_headers(live_client)
    )
    missing_response = live_client.delete(
        f"/api/v1/auth/sessions/{uuid4()}", headers=csrf_headers(live_client)
    )
    assert foreign_response.status_code == missing_response.status_code == 404
    assert foreign_response.json() == missing_response.json() == {"detail": "Session not found."}
    assert live_client.cookies.get(SESSION_COOKIE) == second
    revoked_at = None
    for attempt in range(2):
        response = live_client.delete(
            f"/api/v1/auth/sessions/{first_id}", headers=csrf_headers(live_client)
        )
        assert response.status_code == 204 and "set-cookie" not in response.headers
        assert not client_redis.exists(first_key)
        with Session(concurrent_engine) as database:
            stored = database.get(SessionModel, first_id)
            assert stored and stored.revoked_at
            if attempt == 0:
                revoked_at = stored.revoked_at
            else:
                assert stored.revoked_at == revoked_at
    assert len(live_client.get("/api/v1/auth/sessions").json()) == 1
    live_client.cookies.set(SESSION_COOKIE, first, domain="testserver.local", path="/")
    assert live_client.get("/api/v1/auth/sessions").status_code == 401
    live_client.cookies.set(SESSION_COOKIE, second, domain="testserver.local", path="/")
    response = live_client.delete(
        f"/api/v1/auth/sessions/{second_id}", headers=csrf_headers(live_client)
    )
    assert response.status_code == 204 and live_client.cookies.get(SESSION_COOKIE) is None
    assert live_client.get("/api/v1/auth/sessions").status_code == 401
    with Session(concurrent_engine) as database:
        foreign_row = database.get(SessionModel, foreign_id)
        assert foreign_row and foreign_row.revoked_at is None


def test_listing_uses_exact_expiry_boundary(concurrent_engine: Engine, settings: Settings) -> None:
    with Session(concurrent_engine) as database, database.begin():
        user = UserModel(email="expiry@example.com")
        database.add(user)
        database.flush()
        repository = SqlAlchemySessionRepository(database)
        cache = create_autospec(SessionCache, instance=True)
        issued = service(repository, cache, settings).create(user.id)
        assert repository.list_active_for_user(user.id, NOW) == [issued.session]
        assert repository.list_active_for_user(user.id, NOW - timedelta(microseconds=1)) == []
        assert repository.list_active_for_user(user.id, issued.session.expires_at) == []
        assert repository.list_active_for_user(uuid4(), NOW) == []


def test_live_revocation_cache_failure_rolls_back(
    live_client: TestClient,
    concurrent_engine: Engine,
    password_hash: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user(concurrent_engine, "student@example.com", password_hash)
    token = browser_login(live_client)
    session_id = live_client.get("/api/v1/auth/sessions").json()[0]["id"]
    client_redis: Redis = cast(FastAPI, live_client.app).state.redis
    key = f"ukladen:auth:session:{hash_token(token)}"
    with monkeypatch.context() as patch:
        patch.setattr(
            client_redis, "delete", Mock(side_effect=RedisConnectionError("private details"))
        )
        response = live_client.delete(
            f"/api/v1/auth/sessions/{session_id}", headers=csrf_headers(live_client)
        )
    assert response.status_code == 503 and "private" not in response.text
    assert "set-cookie" not in response.headers and live_client.cookies.get(SESSION_COOKIE) == token
    with Session(concurrent_engine) as database:
        stored = database.get(SessionModel, UUID(session_id))
        assert stored and stored.revoked_at is None
    assert client_redis.exists(key)
    response = live_client.delete(
        f"/api/v1/auth/sessions/{session_id}", headers=csrf_headers(live_client)
    )
    assert response.status_code == 204 and live_client.cookies.get(SESSION_COOKIE) is None
    assert not client_redis.exists(key)
