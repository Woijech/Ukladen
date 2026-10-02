import os
from dataclasses import replace
from datetime import timedelta
from typing import cast
from unittest.mock import Mock, create_autospec
from uuid import uuid4

import pytest
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import Connection, Engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from test_auth_login import PASSWORD
from test_auth_login import password_hash as password_hash
from test_auth_password_recovery import NEW_PASSWORD, NOW, recovery, seed
from test_auth_password_recovery import recovery_service as recovery_service
from test_auth_persistence import database_connection as database_connection
from test_auth_sessions import concurrent_engine as concurrent_engine
from test_auth_sessions import settings as settings

from app.core.config import Settings
from app.modules.auth.application.password_recovery import PasswordRecoveryService
from app.modules.auth.application.ports import (
    SessionCache,
    SessionCacheUnavailable,
    SessionRepository,
)
from app.modules.auth.application.service import SessionService
from app.modules.auth.domain.entities import AuthSession
from app.modules.auth.domain.errors import InvalidCredentials, InvalidPassword, InvalidSession
from app.modules.auth.infrastructure.orm import CredentialModel, SessionModel
from app.modules.auth.infrastructure.password_hasher import Argon2PasswordHasher
from app.modules.auth.infrastructure.session_cache import RedisSessionCache
from app.modules.auth.infrastructure.token_service import generate_token, hash_token
from app.modules.users.infrastructure.orm import UserModel


def test_change_verifies_current_password_and_keeps_current_session(
    recovery_service: PasswordRecoveryService,
) -> None:
    passwords = cast(Mock, recovery_service.passwords)
    credentials = cast(Mock, recovery_service.credentials)
    sessions = cast(Mock, recovery_service.sessions)
    passwords.verify.return_value = True
    user_id, session_id = uuid4(), uuid4()
    recovery_service.change_password(user_id, session_id, " legacy ", NEW_PASSWORD)
    passwords.verify.assert_called_once_with(" legacy ", "old-hash")
    passwords.hash.assert_called_once_with(NEW_PASSWORD)
    credentials.update_password_hash.assert_called_once_with(user_id, "new-hash", NOW)
    sessions.revoke_others_for_user.assert_called_once_with(user_id, session_id)
    sessions.revoke_all_for_user.assert_not_called()
    assert not cast(Mock, recovery_service.repository).mock_calls


@pytest.mark.parametrize("state", ["disabled", "no_credential", "wrong_password", "update_failed"])
def test_change_rejects_invalid_credentials_generically(
    recovery_service: PasswordRecoveryService, state: str
) -> None:
    users = cast(Mock, recovery_service.users)
    passwords = cast(Mock, recovery_service.passwords)
    credentials = cast(Mock, recovery_service.credentials)
    passwords.verify.return_value = True
    if state == "disabled":
        users.lock_active.return_value = False
    elif state == "no_credential":
        credentials.get_password_hash.return_value = None
    elif state == "wrong_password":
        passwords.verify.return_value = False
    else:
        credentials.update_password_hash.return_value = False
    with pytest.raises(InvalidCredentials, match="^Invalid current password\\.$"):
        recovery_service.change_password(uuid4(), uuid4(), PASSWORD, NEW_PASSWORD)
    cast(Mock, recovery_service.sessions).revoke_others_for_user.assert_not_called()
    if state != "update_failed":
        credentials.update_password_hash.assert_not_called()


@pytest.mark.parametrize("field", ["empty_current", "long_current", "short_new", "long_new"])
def test_change_bounds_passwords_before_io(
    recovery_service: PasswordRecoveryService, field: str
) -> None:
    old = "" if field == "empty_current" else "x" * 1025 if field == "long_current" else PASSWORD
    new = "x" * 11 if field == "short_new" else "x" * 1025 if field == "long_new" else NEW_PASSWORD
    with pytest.raises(InvalidCredentials if field.endswith("current") else InvalidPassword):
        recovery_service.change_password(uuid4(), uuid4(), old, new)
    assert not cast(Mock, recovery_service.users).mock_calls
    assert not cast(Mock, recovery_service.credentials).mock_calls
    assert not cast(Mock, recovery_service.passwords).mock_calls


@pytest.mark.parametrize(
    "state", ["missing", "expired", "future", "revoked", "expires_while_locked"]
)
def test_revoke_others_requires_active_owned_session(settings: Settings, state: str) -> None:
    repository = create_autospec(SessionRepository, instance=True)
    cache = create_autospec(SessionCache, instance=True)
    sessions = SessionService(
        repository,
        cache,
        settings,
        generate_token=generate_token,
        hash_token=hash_token,
        now=lambda: NOW,
    )
    current = AuthSession(
        id=uuid4(),
        user_id=uuid4(),
        token_hash=hash_token(generate_token()),
        created_at=NOW,
        last_seen_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    invalid = current
    if state == "expired":
        invalid = replace(current, created_at=NOW - timedelta(hours=1), expires_at=NOW)
    elif state == "future":
        invalid = replace(current, created_at=NOW + timedelta(minutes=1))
    elif state == "revoked":
        invalid = replace(current, revoked_at=NOW)
    repository.get_for_user.return_value = None if state == "missing" else invalid
    if state == "expires_while_locked":

        def acquire_lock(session_id: object, user_id: object) -> AuthSession:
            sessions.now = lambda: current.expires_at
            return current

        repository.get_for_user.side_effect = acquire_lock
    with pytest.raises(InvalidSession):
        sessions.revoke_others_for_user(current.user_id, current.id)
    repository.get_for_user.assert_called_once_with(current.id, current.user_id)
    repository.revoke_others_for_user.assert_not_called()
    cache.delete.assert_not_called()


@pytest.mark.parametrize(
    "state",
    [
        "foreign",
        "missing",
        "expired",
        "revoked",
        "future",
        "malformed_hash",
        "disabled",
        "no_credential",
    ],
)
def test_database_rejections_roll_back_password(
    database_connection: Connection, settings: Settings, password_hash: str, state: str
) -> None:
    cache = create_autospec(SessionCache, instance=True)
    with Session(database_connection, join_transaction_mode="create_savepoint") as database:
        with database.begin():
            user_id = seed(database, password_hash)
            other_id = seed(database, password_hash, "other@example.com")
            service = recovery(database, settings, cache)
            current = service.sessions.create(other_id if state == "foreign" else user_id)
            row = database.get(SessionModel, current.session.id)
            assert row
            if state == "expired":
                row.created_at = row.last_seen_at = NOW - timedelta(hours=1)
                row.expires_at = NOW
            elif state == "revoked":
                row.revoked_at = NOW
            elif state == "future":
                row.created_at = row.last_seen_at = NOW + timedelta(hours=1)
            credential = database.get(CredentialModel, user_id)
            assert credential
            if state == "malformed_hash":
                credential.password_hash = "malformed"
            elif state == "no_credential":
                database.delete(credential)
            elif state == "disabled":
                user = database.get(UserModel, user_id)
                assert user
                user.status = "disabled"
        # A cached active snapshot must not bypass the canonical current-session check.
        cache.get.return_value = current.session
        expected = (
            InvalidCredentials
            if state in ("malformed_hash", "disabled", "no_credential")
            else InvalidSession
        )
        with pytest.raises(expected), database.begin():
            service.change_password(
                user_id,
                uuid4() if state == "missing" else current.session.id,
                PASSWORD,
                NEW_PASSWORD,
            )
        with database.begin():
            stored = database.get(CredentialModel, user_id, populate_existing=True)
            if state == "no_credential":
                assert stored is None
            else:
                assert stored and stored.password_hash == (
                    "malformed" if state == "malformed_hash" else password_hash
                )
        cache.delete.assert_not_called()
        cache.get.assert_not_called()


@pytest.mark.parametrize("fail_invalidation", [False, True])
def test_live_change_retains_current_and_rolls_back_on_cache_failure(
    concurrent_engine: Engine,
    settings: Settings,
    password_hash: str,
    monkeypatch: pytest.MonkeyPatch,
    fail_invalidation: bool,
) -> None:
    url = os.environ.get("AUTH_TEST_REDIS_URL")
    if not url:
        pytest.skip("Set AUTH_TEST_REDIS_URL to run password-change cache checks.")
    with Redis.from_url(url, socket_connect_timeout=3, socket_timeout=3) as redis:
        cache = RedisSessionCache(redis)
        keys: list[str] = []
        try:
            with Session(concurrent_engine) as database, database.begin():
                user_id = seed(database, password_hash)
                other_id = seed(database, password_hash, "other@example.com")
                service = recovery(database, settings, cache)
                issued = [
                    service.sessions.create(user_id),
                    service.sessions.create(user_id),
                    service.sessions.create(other_id),
                ]
            keys = [f"ukladen:auth:session:{item.session.token_hash}" for item in issued]
            for item in issued:
                cache.set(item.session)
            current_id = issued[0].session.id
            with Session(concurrent_engine) as database:
                service = recovery(database, settings, cache)
                if fail_invalidation:
                    with monkeypatch.context() as patch:
                        patch.setattr(
                            redis,
                            "delete",
                            Mock(side_effect=RedisConnectionError("private details")),
                        )
                        with pytest.raises(SessionCacheUnavailable), database.begin():
                            service.change_password(user_id, current_id, PASSWORD, NEW_PASSWORD)
                    with database.begin():
                        stored = database.get(CredentialModel, user_id)
                        assert stored and stored.password_hash == password_hash
                        assert all(
                            row.revoked_at is None for row in database.scalars(select(SessionModel))
                        )
                    assert all(redis.exists(key) for key in keys)
                with database.begin():
                    service.change_password(user_id, current_id, PASSWORD, NEW_PASSWORD)
                with database.begin():
                    stored = database.get(CredentialModel, user_id, populate_existing=True)
                    assert stored and Argon2PasswordHasher().verify(
                        NEW_PASSWORD, stored.password_hash
                    )
                    assert not Argon2PasswordHasher().verify(PASSWORD, stored.password_hash)
                    assert not Argon2PasswordHasher().verify(
                        NEW_PASSWORD.strip(), stored.password_hash
                    )
                    assert stored.created_at == NOW - timedelta(days=1)
                    assert stored.updated_at == stored.password_updated_at == NOW
                    for item, revoked in zip(issued, (False, True, False), strict=True):
                        row = database.get(SessionModel, item.session.id, populate_existing=True)
                        assert row and (row.revoked_at is not None) == revoked
                assert cache.get(issued[0].session.token_hash) == issued[0].session
                assert cache.get(issued[2].session.token_hash) == issued[2].session
                assert cache.get(issued[1].session.token_hash) is None
                with database.begin():
                    assert service.sessions.validate(issued[0].token) == issued[0].session
                with pytest.raises(InvalidSession), database.begin():
                    service.sessions.validate(issued[1].token)
        finally:
            if keys:
                redis.delete(*keys)


def test_change_without_other_sessions_needs_no_cache_delete(
    database_connection: Connection, settings: Settings, password_hash: str
) -> None:
    redis = create_autospec(Redis, instance=True)
    redis.delete.side_effect = RedisConnectionError("offline")
    with (
        Session(database_connection, join_transaction_mode="create_savepoint") as database,
        database.begin(),
    ):
        user_id = seed(database, password_hash)
        service = recovery(database, settings, RedisSessionCache(redis))
        current = service.sessions.create(user_id)
        service.change_password(user_id, current.session.id, PASSWORD, NEW_PASSWORD)
    redis.delete.assert_not_called()


@pytest.mark.parametrize("commit", [False, True])
def test_concurrent_change_rechecks_password_after_lock(
    concurrent_engine: Engine, settings: Settings, password_hash: str, commit: bool
) -> None:
    cache = create_autospec(SessionCache, instance=True)
    with Session(concurrent_engine) as database, database.begin():
        user_id = seed(database, password_hash)
        current = recovery(database, settings, cache).sessions.create(user_id)
    with Session(concurrent_engine) as winner, Session(concurrent_engine) as contender:
        recovery(winner, settings, cache).change_password(
            user_id, current.session.id, PASSWORD, NEW_PASSWORD
        )
        with pytest.raises(OperationalError, match="lock timeout"), contender.begin():
            contender.execute(text("SET LOCAL lock_timeout = '100ms'"))
            recovery(contender, settings, cache).change_password(
                user_id, current.session.id, PASSWORD, NEW_PASSWORD
            )
        # The retained canonical session is locked until transaction completion too.
        with pytest.raises(OperationalError, match="lock timeout"), contender.begin():
            contender.execute(text("SET LOCAL lock_timeout = '100ms'"))
            database_row = contender.scalar(
                select(SessionModel).where(SessionModel.id == current.session.id).with_for_update()
            )
            assert database_row
        if commit:
            winner.commit()
            with pytest.raises(InvalidCredentials), contender.begin():
                recovery(contender, settings, cache).change_password(
                    user_id, current.session.id, PASSWORD, NEW_PASSWORD
                )
        else:
            winner.rollback()
            with contender.begin():
                recovery(contender, settings, cache).change_password(
                    user_id, current.session.id, PASSWORD, NEW_PASSWORD
                )
