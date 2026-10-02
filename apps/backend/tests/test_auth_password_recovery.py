import os
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, NonCallableMock, create_autospec
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import Connection, Engine, func, select, text, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from test_auth_login import PASSWORD
from test_auth_login import password_hash as password_hash
from test_auth_persistence import database_connection as database_connection
from test_auth_sessions import concurrent_engine as concurrent_engine
from test_auth_sessions import settings as settings

from app.core.config import Settings
from app.modules.auth.application.password_recovery import PasswordRecoveryService
from app.modules.auth.application.ports import (
    CredentialRepository,
    PasswordHasher,
    PasswordResetRepository,
    SessionCache,
    SessionCacheUnavailable,
)
from app.modules.auth.application.service import SessionService
from app.modules.auth.domain.entities import OneTimeToken, TokenType
from app.modules.auth.domain.errors import InvalidOneTimeToken, InvalidPassword
from app.modules.auth.infrastructure.orm import CredentialModel, OneTimeTokenModel, SessionModel
from app.modules.auth.infrastructure.password_hasher import Argon2PasswordHasher
from app.modules.auth.infrastructure.repository import (
    SqlAlchemyCredentialRepository,
    SqlAlchemyPasswordResetRepository,
    SqlAlchemySessionRepository,
)
from app.modules.auth.infrastructure.session_cache import RedisSessionCache
from app.modules.auth.infrastructure.token_service import generate_token, hash_token
from app.modules.users.application.ports import UserAuthentication
from app.modules.users.infrastructure.orm import UserModel
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication

NOW = datetime.now(UTC)
TOKEN = generate_token()
NEW_PASSWORD = "  новый-password-123  "


@pytest.fixture
def recovery_service(settings: Settings) -> PasswordRecoveryService:
    users = create_autospec(UserAuthentication, instance=True)
    users.get_active_id_by_email.return_value = uuid4()
    users.lock_active.return_value = True
    credentials = create_autospec(CredentialRepository, instance=True)
    credentials.get_password_hash.return_value = "old-hash"
    credentials.update_password_hash.return_value = True
    repository = create_autospec(PasswordResetRepository, instance=True)
    repository.get_by_token_hash.return_value = OneTimeToken(
        id=uuid4(),
        user_id=users.get_active_id_by_email.return_value,
        token_type=TokenType.PASSWORD_RESET,
        token_hash=hash_token(TOKEN),
        created_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    passwords = create_autospec(PasswordHasher, instance=True)
    passwords.hash.return_value = "new-hash"
    return PasswordRecoveryService(
        users,
        credentials,
        repository,
        passwords,
        create_autospec(SessionService, instance=True),
        settings,
        generate_token=lambda: TOKEN,
        hash_token=hash_token,
        now=lambda: NOW,
    )


def recovery(database: Session, settings: Settings, cache: SessionCache) -> PasswordRecoveryService:
    sessions = SessionService(
        SqlAlchemySessionRepository(database),
        cache,
        settings,
        generate_token=generate_token,
        hash_token=hash_token,
        now=lambda: NOW,
    )
    return PasswordRecoveryService(
        SqlAlchemyUserAuthentication(database),
        SqlAlchemyCredentialRepository(database),
        SqlAlchemyPasswordResetRepository(database),
        Argon2PasswordHasher(),
        sessions,
        settings,
        generate_token=generate_token,
        hash_token=hash_token,
        now=lambda: NOW,
    )


def seed(database: Session, password_hash: str, email: str = "student@example.com") -> UUID:
    user = UserModel(email=email)
    database.add(user)
    database.flush()
    database.add(
        CredentialModel(
            user_id=user.id,
            password_hash=password_hash,
            created_at=NOW - timedelta(days=1),
            updated_at=NOW - timedelta(days=1),
            password_updated_at=NOW - timedelta(days=1),
        )
    )
    database.flush()
    return user.id


def test_request_returns_hidden_delivery_and_hash_only_storage(
    recovery_service: PasswordRecoveryService, settings: Settings
) -> None:
    result = recovery_service.request_reset(" Student@Example.COM ")
    assert result and result.email == "student@example.com" and result.token == TOKEN
    assert result.expires_at == NOW + timedelta(hours=1) and TOKEN not in repr(result)
    repository = recovery_service.repository
    assert isinstance(repository, NonCallableMock)
    stored = repository.create.call_args.args[0]
    assert stored.token_hash == hash_token(TOKEN) and stored.token_type == TokenType.PASSWORD_RESET
    assert TOKEN not in repr(stored) and stored.used_at is None
    assert Settings.model_fields["auth_password_reset_ttl_seconds"].default == 3600
    with pytest.raises(ValidationError):
        Settings.model_validate(settings.model_dump() | {"auth_password_reset_ttl_seconds": 0})
    recovery_service.lifetime = timedelta(seconds=120)
    result = recovery_service.request_reset("student@example.com")
    assert result and result.expires_at == NOW + timedelta(seconds=120)


@pytest.mark.parametrize("state", ["invalid", "unknown", "no_credential"])
def test_ineligible_requests_do_not_issue_tokens(
    recovery_service: PasswordRecoveryService, state: str
) -> None:
    assert isinstance(recovery_service.users, NonCallableMock)
    assert isinstance(recovery_service.credentials, NonCallableMock)
    if state == "unknown":
        recovery_service.users.get_active_id_by_email.return_value = None
    elif state == "no_credential":
        recovery_service.credentials.get_password_hash.return_value = None
    assert (
        recovery_service.request_reset("invalid" if state == "invalid" else "student@example.com")
        is None
    )
    assert isinstance(recovery_service.repository, NonCallableMock)
    recovery_service.repository.create.assert_not_called()


@pytest.mark.parametrize("token", ["", "x" * 42, "x" * 44, "!" * 43])
def test_malformed_reset_tokens_fail_before_io(
    recovery_service: PasswordRecoveryService, token: str
) -> None:
    with pytest.raises(InvalidOneTimeToken):
        recovery_service.confirm_reset(token, NEW_PASSWORD)
    for dependency in (
        recovery_service.passwords,
        recovery_service.repository,
        recovery_service.users,
    ):
        assert isinstance(dependency, NonCallableMock) and not dependency.mock_calls


@pytest.mark.parametrize("password", ["x" * 11, "x" * 1025])
def test_new_password_policy_precedes_io(
    recovery_service: PasswordRecoveryService, password: str
) -> None:
    with pytest.raises(InvalidPassword):
        recovery_service.confirm_reset(TOKEN, password)
    assert (
        isinstance(recovery_service.passwords, NonCallableMock)
        and not recovery_service.passwords.mock_calls
    )
    assert (
        isinstance(recovery_service.repository, NonCallableMock)
        and not recovery_service.repository.mock_calls
    )
    recovery_service.minimum_password_length = 5
    recovery_service.confirm_reset(TOKEN, "x" * 5)


@pytest.mark.parametrize(
    "state", ["unknown", "expired", "future", "used", "wrong_type", "disabled", "no_credential"]
)
def test_invalid_confirmation_does_not_update_or_revoke(
    recovery_service: PasswordRecoveryService, state: str
) -> None:
    repository, users, credentials, sessions = (
        recovery_service.repository,
        recovery_service.users,
        recovery_service.credentials,
        recovery_service.sessions,
    )
    assert isinstance(repository, NonCallableMock) and isinstance(users, NonCallableMock)
    assert isinstance(credentials, NonCallableMock) and isinstance(sessions, NonCallableMock)
    stored = repository.get_by_token_hash.return_value
    if state == "unknown":
        repository.get_by_token_hash.return_value = None
    elif state == "expired":
        stored.expires_at = NOW
    elif state == "future":
        stored.created_at = NOW + timedelta(minutes=1)
    elif state == "used":
        stored.used_at = NOW
    elif state == "wrong_type":
        stored.token_type = TokenType.EMAIL_VERIFICATION
    elif state == "disabled":
        users.lock_active.return_value = False
    else:
        credentials.get_password_hash.return_value = None
    with pytest.raises(InvalidOneTimeToken) as error:
        recovery_service.confirm_reset(TOKEN, NEW_PASSWORD)
    assert str(error.value) == "Invalid or expired token." and TOKEN not in str(error.value)
    repository.get_by_token_hash.assert_called_once_with(hash_token(TOKEN))
    repository.mark_used.assert_not_called()
    credentials.update_password_hash.assert_not_called()
    sessions.revoke_all_for_user.assert_not_called()


def test_expiry_is_checked_after_user_and_credential_locks(
    recovery_service: PasswordRecoveryService,
) -> None:
    credentials = recovery_service.credentials
    assert isinstance(credentials, NonCallableMock)

    def acquire_credential_lock(user_id: UUID) -> str:
        recovery_service.now = lambda: NOW + timedelta(hours=1)
        return "old-hash"

    credentials.get_password_hash.side_effect = acquire_credential_lock
    with pytest.raises(InvalidOneTimeToken):
        recovery_service.confirm_reset(TOKEN, NEW_PASSWORD)
    credentials.update_password_hash.assert_not_called()


def test_success_consumes_once_and_preserves_password(
    recovery_service: PasswordRecoveryService,
) -> None:
    repository, credentials, passwords, sessions = (
        recovery_service.repository,
        recovery_service.credentials,
        recovery_service.passwords,
        recovery_service.sessions,
    )
    assert all(
        isinstance(item, NonCallableMock) for item in (repository, credentials, passwords, sessions)
    )
    assert isinstance(repository, NonCallableMock) and isinstance(credentials, NonCallableMock)
    assert isinstance(passwords, NonCallableMock) and isinstance(sessions, NonCallableMock)
    stored = repository.get_by_token_hash.return_value
    assert recovery_service.confirm_reset(TOKEN, NEW_PASSWORD) == stored.user_id
    passwords.hash.assert_called_once_with(NEW_PASSWORD)
    credentials.update_password_hash.assert_called_once_with(stored.user_id, "new-hash", NOW)
    repository.mark_used.assert_called_once_with(stored.id, NOW)
    sessions.revoke_all_for_user.assert_called_once_with(stored.user_id)
    with pytest.raises(InvalidOneTimeToken):
        recovery_service.confirm_reset(TOKEN, NEW_PASSWORD)
    assert (
        credentials.update_password_hash.call_count == sessions.revoke_all_for_user.call_count == 1
    )


@pytest.mark.parametrize(
    "state", ["disabled", "no_credential", "expired", "used", "future", "wrong_type"]
)
def test_database_rejections_preserve_credentials_and_token(
    database_connection: Connection, settings: Settings, password_hash: str, state: str
) -> None:
    with Session(database_connection, join_transaction_mode="create_savepoint") as database:
        cache = create_autospec(SessionCache, instance=True)
        service = recovery(database, settings, cache)
        with database.begin():
            user_id = seed(database, password_hash)
            delivery = service.request_reset(" Student@Example.COM ")
            assert delivery
            token = database.scalar(
                select(OneTimeTokenModel).where(
                    OneTimeTokenModel.token_hash == hash_token(delivery.token)
                )
            )
            assert token
            if state == "disabled":
                database.execute(
                    update(UserModel).where(UserModel.id == user_id).values(status="disabled")
                )
                assert service.request_reset("student@example.com") is None
            elif state == "no_credential":
                credential = database.get(CredentialModel, user_id)
                assert credential
                database.delete(credential)
                database.flush()
                assert service.request_reset("student@example.com") is None
            elif state == "expired":
                token.created_at = NOW - timedelta(hours=1)
                token.expires_at = NOW
            elif state == "used":
                token.used_at = NOW
            elif state == "future":
                token.created_at = NOW + timedelta(minutes=1)
            else:
                token.token_type = TokenType.EMAIL_VERIFICATION
        with pytest.raises(InvalidOneTimeToken), database.begin():
            service.confirm_reset(delivery.token, NEW_PASSWORD)
        with database.begin():
            database.refresh(token)
            assert token.used_at == (NOW if state == "used" else None)
            credential = database.get(CredentialModel, user_id)
            assert (
                credential is None
                if state == "no_credential"
                else credential and credential.password_hash == password_hash
            )
            assert database.scalar(select(func.count()).select_from(OneTimeTokenModel)) == 1
        cache.delete.assert_not_called()


@pytest.mark.parametrize("fail_invalidation", [False, True])
def test_live_reset_updates_consumes_and_revokes_atomically(
    concurrent_engine: Engine,
    settings: Settings,
    password_hash: str,
    monkeypatch: pytest.MonkeyPatch,
    fail_invalidation: bool,
) -> None:
    url = os.environ.get("AUTH_TEST_REDIS_URL")
    if not url:
        pytest.skip("Set AUTH_TEST_REDIS_URL to run reset cache integration checks.")
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
                delivery = service.request_reset("student@example.com")
                assert delivery
                assert service.request_reset("unknown@example.com") is None
            keys = [f"ukladen:auth:session:{item.session.token_hash}" for item in issued]
            for item in issued:
                cache.set(item.session)
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
                            service.confirm_reset(delivery.token, NEW_PASSWORD)
                    with database.begin():
                        credential = database.get(CredentialModel, user_id)
                        stored = database.scalar(
                            select(OneTimeTokenModel).where(
                                OneTimeTokenModel.token_hash == hash_token(delivery.token)
                            )
                        )
                        assert credential and credential.password_hash == password_hash
                        assert stored and stored.used_at is None
                        assert all(
                            row.revoked_at is None for row in database.scalars(select(SessionModel))
                        )
                    assert all(redis.exists(key) for key in keys)
                with database.begin():
                    assert service.confirm_reset(delivery.token, NEW_PASSWORD) == user_id
                with database.begin():
                    credential = database.get(CredentialModel, user_id)
                    assert credential and credential.password_hash != password_hash
                    passwords = Argon2PasswordHasher()
                    assert passwords.verify(NEW_PASSWORD, credential.password_hash)
                    assert not passwords.verify(PASSWORD, credential.password_hash)
                    assert not passwords.verify(NEW_PASSWORD.strip(), credential.password_hash)
                    assert credential.created_at == NOW - timedelta(days=1)
                    assert credential.updated_at == credential.password_updated_at == NOW
                    stored = database.scalar(
                        select(OneTimeTokenModel).where(
                            OneTimeTokenModel.token_hash == hash_token(delivery.token)
                        )
                    )
                    assert (
                        stored
                        and stored.used_at == NOW
                        and stored.token_hash == hash_token(delivery.token)
                    )
                    assert [
                        row.revoked_at is not None
                        for item in issued
                        if (row := database.get(SessionModel, item.session.id))
                    ] == [True, True, False]
                with pytest.raises(InvalidOneTimeToken), database.begin():
                    service.confirm_reset(delivery.token, NEW_PASSWORD)
            assert not redis.exists(keys[0]) and not redis.exists(keys[1]) and redis.exists(keys[2])
        finally:
            if keys:
                redis.delete(*keys)


@pytest.mark.parametrize("commit", [False, True])
def test_concurrent_reset_has_one_winner(
    concurrent_engine: Engine, settings: Settings, password_hash: str, commit: bool
) -> None:
    cache = create_autospec(SessionCache, instance=True)
    with Session(concurrent_engine) as database, database.begin():
        user_id = seed(database, password_hash)
        delivery = recovery(database, settings, cache).request_reset("student@example.com")
        assert delivery
    with Session(concurrent_engine) as winner, Session(concurrent_engine) as contender:
        assert (
            recovery(winner, settings, cache).confirm_reset(delivery.token, NEW_PASSWORD) == user_id
        )
        with pytest.raises(OperationalError, match="lock timeout"), contender.begin():
            contender.execute(text("SET LOCAL lock_timeout = '100ms'"))
            recovery(contender, settings, cache).confirm_reset(delivery.token, NEW_PASSWORD)
        # Confirmation also holds canonical user and credential locks until commit.
        for model, values in (
            (UserModel, {"status": "disabled"}),
            (CredentialModel, {"password_hash": "changed"}),
        ):
            with pytest.raises(OperationalError, match="lock timeout"), contender.begin():
                contender.execute(text("SET LOCAL lock_timeout = '100ms'"))
                key = UserModel.id if model is UserModel else CredentialModel.user_id
                contender.execute(update(model).where(key == user_id).values(**values))
        if commit:
            winner.commit()
            with pytest.raises(InvalidOneTimeToken), contender.begin():
                recovery(contender, settings, cache).confirm_reset(delivery.token, NEW_PASSWORD)
        else:
            winner.rollback()
            with contender.begin():
                assert (
                    recovery(contender, settings, cache).confirm_reset(delivery.token, NEW_PASSWORD)
                    == user_id
                )
