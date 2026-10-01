from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from unittest.mock import create_autospec, patch

import pytest
from pydantic import ValidationError
from sqlalchemy import Connection, func, select
from sqlalchemy.orm import Session
from test_auth_persistence import database_connection as database_connection
from test_auth_sessions import cache as cache
from test_auth_sessions import settings as settings

from app.core.config import Settings
from app.modules.auth.application.ports import PasswordHasher, RegistrationRepository, SessionCache
from app.modules.auth.application.registration import RegistrationService
from app.modules.auth.application.service import SessionService
from app.modules.auth.domain.errors import InvalidRegistration, RegistrationConflict
from app.modules.auth.infrastructure.orm import CredentialModel, OneTimeTokenModel, SessionModel
from app.modules.auth.infrastructure.password_hasher import Argon2PasswordHasher
from app.modules.auth.infrastructure.repository import (
    SqlAlchemyRegistrationRepository,
    SqlAlchemySessionRepository,
)
from app.modules.auth.infrastructure.token_service import generate_token, hash_token
from app.modules.users.application.ports import UserRegistration
from app.modules.users.infrastructure.orm import UserModel
from app.modules.users.infrastructure.repository import SqlAlchemyUserRegistration

NOW = datetime(2026, 10, 1, tzinfo=UTC)
PASSWORD = "  registration password Я  "


def registration(database: Session, cache: SessionCache, settings: Settings) -> RegistrationService:
    return RegistrationService(
        SqlAlchemyUserRegistration(database),
        SqlAlchemyRegistrationRepository(database),
        Argon2PasswordHasher(),
        SessionService(
            SqlAlchemySessionRepository(database),
            cache,
            settings,
            generate_token=generate_token,
            hash_token=hash_token,
            now=lambda: NOW,
        ),
        settings,
        generate_token=generate_token,
        hash_token=hash_token,
        now=lambda: NOW,
    )


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("", PASSWORD),
        ("missing-domain", PASSWORD),
        ("name@", PASSWORD),
        ("@example.com", PASSWORD),
        ("name@@example.com", PASSWORD),
        ("User <name@example.com>", PASSWORD),
        ("name@example.com\r\nBcc: other@example.com", PASSWORD),
        ("name@example.com (comment)", PASSWORD),
        ("x" * 309 + "@example.com", PASSWORD),
        ("name@example.com", ""),
        ("name@example.com", "x" * 11),
        ("name@example.com", "x" * 1025),
    ],
)
def test_invalid_registration_has_no_side_effects(
    settings: Settings, email: str, password: str
) -> None:
    users = create_autospec(UserRegistration, instance=True)
    repository = create_autospec(RegistrationRepository, instance=True)
    passwords = create_autospec(PasswordHasher, instance=True)
    sessions = create_autospec(SessionService, instance=True)
    service = RegistrationService(
        users,
        repository,
        passwords,
        sessions,
        settings,
        generate_token=generate_token,
        hash_token=hash_token,
    )
    with pytest.raises(InvalidRegistration):
        service.register(email, password)
    assert not users.mock_calls
    assert not repository.mock_calls
    assert not passwords.mock_calls
    assert not sessions.mock_calls


def test_registration_configuration(settings: Settings) -> None:
    assert Settings.model_fields["auth_password_min_length"].default == 12
    assert Settings.model_fields["auth_email_verification_ttl_seconds"].default == 86400
    for values in (
        {"auth_password_min_length": 0},
        {"auth_password_min_length": 1025},
        {"auth_email_verification_ttl_seconds": 0},
    ):
        with pytest.raises(ValidationError):
            Settings.model_validate(settings.model_dump() | values)


def test_registration_persists_only_hashes(
    database_connection: Connection, cache: SessionCache, settings: Settings
) -> None:
    configured = settings.model_copy(
        update={
            "auth_password_min_length": len(PASSWORD),
            "auth_email_verification_ttl_seconds": 120,
        }
    )
    with Session(database_connection, join_transaction_mode="create_savepoint") as database:
        with database.begin():
            service = registration(database, cache, configured)
            with pytest.raises(InvalidRegistration):
                service.register("name@example.com", PASSWORD[:-1])
            result = service.register(
                "  Student@EXAMPLE.COM  ",
                PASSWORD,
                user_agent="registration-test",
                ip_address=ip_address("2001:db8::1"),
            )
        user = database.get(UserModel, result.user_id)
        credential = database.get(CredentialModel, result.user_id)
        session = database.get(SessionModel, result.session.session.id)
        token = database.scalar(select(OneTimeTokenModel))
        assert user and credential and session and token
        assert user.email == result.email == "student@example.com"
        assert user.status == "active" and user.email_verified_at is None
        assert credential.password_hash.startswith("$argon2id$")
        assert Argon2PasswordHasher().verify(PASSWORD, credential.password_hash)
        assert not Argon2PasswordHasher().verify(PASSWORD.strip(), credential.password_hash)
        assert credential.password_updated_at == NOW
        assert session.user_id == token.user_id == result.user_id
        assert session.token_hash == hash_token(result.session.token)
        assert session.token_hash != result.session.token
        assert session.user_agent == "registration-test"
        assert str(session.ip_address) == "2001:db8::1"
        assert token.token_type == "email_verification" and token.used_at is None
        assert token.token_hash == hash_token(result.verification_token)
        assert token.token_hash != result.verification_token
        assert token.created_at == NOW and token.expires_at == NOW + timedelta(seconds=120)
        assert result.session.token != result.verification_token
        assert PASSWORD not in repr(result)
        assert result.session.token not in repr(result)
        assert result.verification_token not in repr(result)
        assert cache.get(session.token_hash) is None


@pytest.mark.parametrize("has_password", [False, True])
def test_duplicate_email_preserves_existing_account(
    database_connection: Connection, cache: SessionCache, settings: Settings, has_password: bool
) -> None:
    with Session(database_connection, join_transaction_mode="create_savepoint") as database:
        service = registration(database, cache, settings)
        if has_password:
            existing_id = service.register("existing@example.com", PASSWORD).user_id
        else:
            user = UserModel(email="Existing@Example.COM")
            database.add(user)
            database.flush()
            existing_id = user.id
        with pytest.raises(RegistrationConflict) as error:
            service.register("  EXISTING@example.com ", PASSWORD)
        assert str(error.value) == "Email is already registered."
        assert error.value.__suppress_context__
        assert database.scalar(select(func.count()).select_from(UserModel)) == 1
        assert database.get(UserModel, existing_id) is not None
        for model in (CredentialModel, SessionModel, OneTimeTokenModel):
            assert database.scalar(select(func.count()).select_from(model)) == int(has_password)


def test_registration_failure_rolls_back_all_records(
    database_connection: Connection, cache: SessionCache, settings: Settings
) -> None:
    with Session(database_connection, join_transaction_mode="create_savepoint") as database:
        service = registration(database, cache, settings)
        with (
            patch.object(
                service.repository, "create_one_time_token", side_effect=RuntimeError("failure")
            ),
            pytest.raises(RuntimeError, match="failure"),
            database.begin(),
        ):
            service.register("rollback@example.com", PASSWORD)
        for model in (UserModel, CredentialModel, SessionModel, OneTimeTokenModel):
            assert database.scalar(select(func.count()).select_from(model)) == 0
