from ipaddress import ip_address
from unittest.mock import Mock, create_autospec, patch
from uuid import uuid4

import pytest
from sqlalchemy import Connection, Engine, func, select, text, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from test_auth_persistence import database_connection as database_connection
from test_auth_registration import PASSWORD, registration
from test_auth_sessions import cache as cache
from test_auth_sessions import concurrent_engine as concurrent_engine
from test_auth_sessions import settings as settings

from app.core.config import Settings
from app.modules.auth.application.login import LoginService
from app.modules.auth.application.ports import CredentialRepository, PasswordHasher, SessionCache
from app.modules.auth.application.service import SessionService
from app.modules.auth.domain.entities import AuthSession
from app.modules.auth.domain.errors import InvalidCredentials, InvalidSession
from app.modules.auth.infrastructure.orm import CredentialModel, SessionModel
from app.modules.auth.infrastructure.password_hasher import Argon2PasswordHasher
from app.modules.auth.infrastructure.repository import (
    SqlAlchemyCredentialRepository,
    SqlAlchemySessionRepository,
)
from app.modules.auth.infrastructure.token_service import generate_token, hash_token
from app.modules.users.application.ports import UserAuthentication
from app.modules.users.infrastructure.orm import UserModel
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication


@pytest.fixture(scope="module")
def dummy_hash() -> str:
    return Argon2PasswordHasher().hash(generate_token())


@pytest.fixture(scope="module")
def password_hash() -> str:
    return Argon2PasswordHasher().hash(PASSWORD)


def login_service(
    database: Session, cache: SessionCache, settings: Settings, dummy_hash: str
) -> LoginService:
    return LoginService(
        SqlAlchemyUserAuthentication(database),
        SqlAlchemyCredentialRepository(database),
        Argon2PasswordHasher(),
        SessionService(
            SqlAlchemySessionRepository(database),
            cache,
            settings,
            generate_token=generate_token,
            hash_token=hash_token,
        ),
        dummy_password_hash=dummy_hash,
    )


@pytest.mark.parametrize("state", ["unknown", "no_password", "empty_hash", "wrong_password"])
def test_login_failures_have_one_public_error(state: str) -> None:
    users = create_autospec(UserAuthentication, instance=True)
    credentials = create_autospec(CredentialRepository, instance=True)
    passwords = create_autospec(PasswordHasher, instance=True)
    sessions = create_autospec(SessionService, instance=True)
    user_id = None if state == "unknown" else uuid4()
    users.get_active_id_by_email.return_value = user_id
    stored_hash = None if state in ("unknown", "no_password") else "stored-hash"
    if state == "empty_hash":
        stored_hash = ""
    credentials.get_password_hash.return_value = stored_hash
    # Even matching the dummy hash must never authenticate a missing credential.
    passwords.verify.return_value = state != "wrong_password"
    service = LoginService(
        users, credentials, passwords, sessions, dummy_password_hash="dummy-hash"
    )
    with pytest.raises(InvalidCredentials) as error:
        service.login("  Student@Example.COM  ", PASSWORD)
    assert str(error.value) == "Invalid email or password."
    users.get_active_id_by_email.assert_called_once_with("student@example.com")
    passwords.verify.assert_called_once_with(PASSWORD, stored_hash or "dummy-hash")
    if user_id is None:
        credentials.get_password_hash.assert_not_called()
    else:
        credentials.get_password_hash.assert_called_once_with(user_id)
    sessions.create.assert_not_called()


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("", PASSWORD),
        ("not-an-email", PASSWORD),
        ("x" * 309 + "@example.com", PASSWORD),
        ("name@example.com\r\nBcc: other@example.com", PASSWORD),
        ("name@example.com", ""),
        ("name@example.com", "x" * 1025),
    ],
)
def test_login_input_limits_prevent_side_effects(email: str, password: str) -> None:
    users = create_autospec(UserAuthentication, instance=True)
    credentials = create_autospec(CredentialRepository, instance=True)
    passwords = create_autospec(PasswordHasher, instance=True)
    sessions = create_autospec(SessionService, instance=True)
    service = LoginService(
        users, credentials, passwords, sessions, dummy_password_hash="dummy-hash"
    )
    with pytest.raises(InvalidCredentials, match="Invalid email or password"):
        service.login(email, password)
    assert not users.mock_calls and not credentials.mock_calls
    assert not passwords.mock_calls and not sessions.mock_calls


def test_login_does_not_apply_new_registration_minimum() -> None:
    users = create_autospec(UserAuthentication, instance=True)
    credentials = create_autospec(CredentialRepository, instance=True)
    passwords = create_autospec(PasswordHasher, instance=True)
    sessions = create_autospec(SessionService, instance=True)
    user_id = uuid4()
    users.get_active_id_by_email.return_value = user_id
    credentials.get_password_hash.return_value = "stored-hash"
    passwords.verify.return_value = True
    service = LoginService(
        users, credentials, passwords, sessions, dummy_password_hash="dummy-hash"
    )
    assert service.login("student@example.com", "Я") == sessions.create.return_value
    passwords.verify.assert_called_once_with("Я", "stored-hash")
    sessions.create.assert_called_once_with(user_id, user_agent=None, ip_address=None)


def test_login_logout_and_logout_all(
    database_connection: Connection, cache: Mock, settings: Settings, dummy_hash: str
) -> None:
    with Session(database_connection, join_transaction_mode="create_savepoint") as database:
        with database.begin():
            registered = registration(database, cache, settings).register(
                "student@example.com", PASSWORD
            )
            other = registration(database, cache, settings).register("other@example.com", PASSWORD)
        login = login_service(database, cache, settings, dummy_hash)
        with database.begin():
            first = login.login(
                "  STUDENT@Example.COM  ",
                PASSWORD,
                user_agent="login-test",
                ip_address=ip_address("192.0.2.1"),
            )
            second = login.login("student@example.com", PASSWORD)
            assert first.session.user_id == second.session.user_id == registered.user_id
            assert first.token != second.token and first.token not in repr(first)
            stored = database.get(SessionModel, first.session.id)
            assert stored and stored.token_hash == hash_token(first.token)
            assert stored.user_agent == "login-test" and str(stored.ip_address) == "192.0.2.1"
            user = database.get(UserModel, registered.user_id)
            assert user and user.email_verified_at is None
            cache.set.assert_not_called()
        with database.begin():
            for issued in (first, second, other.session):
                assert login.sessions.validate(issued.token) == issued.session
        with database.begin():
            login.sessions.revoke(first.session.id)
        with pytest.raises(InvalidSession), database.begin():
            login.sessions.validate(first.token)
        with database.begin():
            assert login.sessions.validate(second.token) == second.session
        with database.begin():
            login.sessions.revoke_all_for_user(registered.user_id)
        for issued in (registered.session, first, second):
            assert cache.get(issued.session.token_hash) is None
            with pytest.raises(InvalidSession), database.begin():
                login.sessions.validate(issued.token)
        with database.begin():
            assert login.sessions.validate(other.session.token) == other.session.session


@pytest.mark.parametrize(
    "state", ["unknown", "wrong_password", "disabled", "no_password", "malformed_hash"]
)
def test_login_rejects_invalid_accounts_without_creating_sessions(
    database_connection: Connection,
    cache: Mock,
    settings: Settings,
    dummy_hash: str,
    password_hash: str,
    state: str,
) -> None:
    with Session(database_connection, join_transaction_mode="create_savepoint") as database:
        with database.begin():
            user = UserModel(
                email="Existing@Example.COM", status="disabled" if state == "disabled" else "active"
            )
            database.add(user)
            database.flush()
            if state != "no_password":
                database.add(
                    CredentialModel(
                        user_id=user.id,
                        password_hash="malformed" if state == "malformed_hash" else password_hash,
                    )
                )
        with pytest.raises(InvalidCredentials) as error, database.begin():
            login_service(database, cache, settings, dummy_hash).login(
                "unknown@example.com" if state == "unknown" else "  EXISTING@example.com ",
                "incorrect password" if state == "wrong_password" else PASSWORD,
            )
        assert str(error.value) == "Invalid email or password."
        assert database.scalar(select(func.count()).select_from(SessionModel)) == 0
        cache.set.assert_not_called()


def test_login_failure_rolls_back_new_session(
    database_connection: Connection,
    cache: Mock,
    settings: Settings,
    dummy_hash: str,
    password_hash: str,
) -> None:
    with Session(database_connection, join_transaction_mode="create_savepoint") as database:
        with database.begin():
            user = UserModel(email="student@example.com")
            database.add(user)
            database.flush()
            database.add(CredentialModel(user_id=user.id, password_hash=password_hash))
        service = login_service(database, cache, settings, dummy_hash)
        create = service.sessions.repository.create

        def fail_after_create(session: AuthSession) -> None:
            create(session)
            raise RuntimeError("failure")

        with (
            patch.object(service.sessions.repository, "create", side_effect=fail_after_create),
            pytest.raises(RuntimeError, match="failure"),
            database.begin(),
        ):
            service.login("student@example.com", PASSWORD)
        assert database.scalar(select(func.count()).select_from(SessionModel)) == 0
        cache.set.assert_not_called()


@pytest.mark.parametrize("record", ["user", "credential"])
def test_login_locks_authentication_records_until_commit(
    concurrent_engine: Engine,
    cache: Mock,
    settings: Settings,
    dummy_hash: str,
    password_hash: str,
    record: str,
) -> None:
    with Session(concurrent_engine) as database, database.begin():
        user = UserModel(email="student@example.com")
        database.add(user)
        database.flush()
        user_id = user.id
        database.add(CredentialModel(user_id=user_id, password_hash=password_hash))
    mutation = (
        update(UserModel).where(UserModel.id == user_id).values(status="disabled")
        if record == "user"
        else update(CredentialModel)
        .where(CredentialModel.user_id == user_id)
        .values(password_hash=dummy_hash)
    )
    with Session(concurrent_engine) as reader, Session(concurrent_engine) as writer:
        service = login_service(reader, cache, settings, dummy_hash)
        issued = service.login("student@example.com", PASSWORD)
        with pytest.raises(OperationalError, match="lock timeout"), writer.begin():
            writer.execute(text("SET LOCAL lock_timeout = '100ms'"))
            writer.execute(mutation)
        reader.commit()
        with writer.begin():
            writer.execute(mutation)
        with pytest.raises(InvalidCredentials), reader.begin():
            service.login("student@example.com", PASSWORD)
        with reader.begin():
            assert reader.get(SessionModel, issued.session.id) is not None
