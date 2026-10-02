from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, create_autospec, patch
from uuid import uuid4

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from test_auth_persistence import database_connection as database_connection
from test_auth_sessions import concurrent_engine as concurrent_engine

from app.modules.auth.application.ports import EmailVerificationRepository
from app.modules.auth.application.verification import EmailVerificationService
from app.modules.auth.domain.entities import OneTimeToken, TokenType
from app.modules.auth.domain.errors import InvalidOneTimeToken
from app.modules.auth.infrastructure.orm import OneTimeTokenModel
from app.modules.auth.infrastructure.repository import SqlAlchemyEmailVerificationRepository
from app.modules.auth.infrastructure.token_service import generate_token, hash_token
from app.modules.users.application.ports import EmailVerifier
from app.modules.users.infrastructure.orm import UserModel
from app.modules.users.infrastructure.repository import SqlAlchemyEmailVerifier

NOW = datetime(2026, 10, 3, tzinfo=UTC)


def verification(database: Session) -> EmailVerificationService:
    return EmailVerificationService(
        SqlAlchemyEmailVerificationRepository(database),
        SqlAlchemyEmailVerifier(database),
        hash_token=hash_token,
        now=lambda: NOW,
    )


def seed(database: Session) -> tuple[UserModel, OneTimeTokenModel, str]:
    user = UserModel(email="verification@example.com")
    database.add(user)
    database.flush()
    raw_token = generate_token()
    token = OneTimeTokenModel(
        user_id=user.id,
        token_type=TokenType.EMAIL_VERIFICATION,
        token_hash=hash_token(raw_token),
        created_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(hours=1),
    )
    database.add(token)
    database.flush()
    return user, token, raw_token


@pytest.mark.parametrize("token", ["", "x" * 42, "x" * 44, "!" * 43])
def test_malformed_verification_token_has_no_side_effects(token: str) -> None:
    repository = create_autospec(EmailVerificationRepository, instance=True)
    users = create_autospec(EmailVerifier, instance=True)
    service = EmailVerificationService(repository, users, hash_token=hash_token)
    with pytest.raises(InvalidOneTimeToken, match="Invalid or expired token"):
        service.confirm(token)
    assert not repository.mock_calls and not users.mock_calls


def test_verification_uses_hash_and_sanitized_errors() -> None:
    repository = create_autospec(EmailVerificationRepository, instance=True)
    users = create_autospec(EmailVerifier, instance=True)
    service = EmailVerificationService(repository, users, hash_token=hash_token, now=lambda: NOW)
    token = generate_token()
    repository.get_by_token_hash.return_value = None
    with pytest.raises(InvalidOneTimeToken) as error:
        service.confirm(token)
    assert token not in str(error.value)
    repository.get_by_token_hash.assert_called_once_with(hash_token(token))
    repository.mark_used.assert_not_called()
    users.mark_verified.assert_not_called()
    user_id = uuid4()
    stored = OneTimeToken(
        id=uuid4(),
        user_id=user_id,
        token_type=TokenType.EMAIL_VERIFICATION,
        token_hash=hash_token(token),
        created_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    repository.get_by_token_hash.return_value = stored
    users.mark_verified.return_value = True
    assert service.confirm(token) == user_id
    repository.mark_used.assert_called_once_with(stored.id, NOW)
    users.mark_verified.assert_called_once_with(user_id, NOW)
    stored.used_at = None
    service.now = lambda: NOW.replace(tzinfo=None)
    repository.reset_mock()
    users.reset_mock()
    with pytest.raises(ValueError, match="timezone-aware"):
        service.confirm(token)
    repository.mark_used.assert_not_called()
    assert not users.mock_calls


def test_expiry_is_checked_after_acquiring_token_lock() -> None:
    repository = create_autospec(EmailVerificationRepository, instance=True)
    users = create_autospec(EmailVerifier, instance=True)
    token = generate_token()
    stored = OneTimeToken(
        id=uuid4(),
        user_id=uuid4(),
        token_type=TokenType.EMAIL_VERIFICATION,
        token_hash=hash_token(token),
        created_at=NOW,
        expires_at=NOW + timedelta(seconds=1),
    )
    clock = Mock(return_value=NOW)

    def acquire_lock(token_hash: str) -> OneTimeToken:
        assert token_hash == stored.token_hash
        clock.assert_not_called()
        clock.return_value = stored.expires_at
        return stored

    repository.get_by_token_hash.side_effect = acquire_lock
    service = EmailVerificationService(repository, users, hash_token=hash_token, now=clock)
    with pytest.raises(InvalidOneTimeToken):
        service.confirm(token)
    repository.mark_used.assert_not_called()
    users.mark_verified.assert_not_called()


@pytest.mark.parametrize("already_verified", [False, True])
def test_confirmation_and_replay(database_connection: Connection, already_verified: bool) -> None:
    with Session(database_connection, join_transaction_mode="create_savepoint") as database:
        with database.begin():
            user, token, raw_token = seed(database)
            first_verification = NOW - timedelta(days=1) if already_verified else None
            user.email_verified_at = first_verification
            user.status = "disabled" if already_verified else "active"
            database.flush()
            assert verification(database).confirm(raw_token) == user.id
        with database.begin():
            database.refresh(user)
            database.refresh(token)
            assert user.email_verified_at == (first_verification or NOW)
            assert user.status == ("disabled" if already_verified else "active")
            assert token.used_at == NOW
        with pytest.raises(InvalidOneTimeToken), database.begin():
            verification(database).confirm(raw_token)


@pytest.mark.parametrize("state", ["unknown", "expired", "future", "used", "password_reset"])
def test_invalid_verification_tokens_do_not_verify_user(
    database_connection: Connection, state: str
) -> None:
    with Session(database_connection, join_transaction_mode="create_savepoint") as database:
        with database.begin():
            user, token, raw_token = seed(database)
            if state == "unknown":
                raw_token = generate_token()
            elif state == "expired":
                token.expires_at = NOW
            elif state == "future":
                token.created_at = NOW + timedelta(minutes=1)
            elif state == "used":
                token.used_at = NOW - timedelta(minutes=1)
            else:
                token.token_type = TokenType.PASSWORD_RESET
        with pytest.raises(InvalidOneTimeToken), database.begin():
            verification(database).confirm(raw_token)
        database.refresh(user)
        database.refresh(token)
        assert user.email_verified_at is None
        assert token.used_at == (NOW - timedelta(minutes=1) if state == "used" else None)


@pytest.mark.parametrize("raises", [False, True])
def test_failed_user_update_rolls_back_consumption(
    database_connection: Connection, raises: bool
) -> None:
    with Session(database_connection, join_transaction_mode="create_savepoint") as database:
        with database.begin():
            user, token, raw_token = seed(database)
        service = verification(database)
        with (
            patch.object(
                service.users,
                "mark_verified",
                return_value=False,
                side_effect=RuntimeError("failure") if raises else None,
            ),
            pytest.raises(RuntimeError if raises else InvalidOneTimeToken),
            database.begin(),
        ):
            service.confirm(raw_token)
        with database.begin():
            database.refresh(user)
            database.refresh(token)
            assert token.used_at is None and user.email_verified_at is None
            assert service.confirm(raw_token) == user.id


@pytest.mark.parametrize("commit", [False, True])
def test_concurrent_confirmation_has_one_winner(concurrent_engine: Engine, commit: bool) -> None:
    with Session(concurrent_engine) as database, database.begin():
        user, token, raw_token = seed(database)
        user_id, token_id = user.id, token.id
    with Session(concurrent_engine) as winner, Session(concurrent_engine) as contender:
        assert verification(winner).confirm(raw_token) == user_id
        with pytest.raises(OperationalError, match="lock timeout"), contender.begin():
            contender.execute(text("SET LOCAL lock_timeout = '100ms'"))
            verification(contender).confirm(raw_token)
        if commit:
            winner.commit()
            with pytest.raises(InvalidOneTimeToken), contender.begin():
                verification(contender).confirm(raw_token)
        else:
            winner.rollback()
            with contender.begin():
                assert verification(contender).confirm(raw_token) == user_id
    with Session(concurrent_engine) as database:
        stored_user = database.get(UserModel, user_id)
        stored_token = database.get(OneTimeTokenModel, token_id)
        assert stored_user and stored_token
        assert stored_user.email_verified_at == stored_token.used_at == NOW
