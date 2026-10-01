import os
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from pwdlib import PasswordHash
from sqlalchemy import Connection, create_engine, func, insert, inspect, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema

from alembic import command
from app.modules.auth.application.ports import SessionRepository
from app.modules.auth.domain.entities import AuthSession
from app.modules.auth.domain.errors import InvalidSession
from app.modules.auth.infrastructure.orm import (
    CredentialModel,
    IdentityModel,
    OneTimeTokenModel,
    SessionModel,
)
from app.modules.auth.infrastructure.repository import SqlAlchemySessionRepository
from app.modules.users.infrastructure.orm import UserModel


def migration_config(connection: Connection) -> Config:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


@pytest.fixture
def database_connection() -> Iterator[Connection]:
    url = os.environ.get("AUTH_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set AUTH_TEST_DATABASE_URL to run PostgreSQL persistence checks.")
    engine = create_engine(url, connect_args={"connect_timeout": 3})
    schema = f"auth_test_{uuid4().hex}"
    try:
        with engine.connect() as connection, connection.begin() as transaction:
            connection.execute(CreateSchema(schema))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
            connection.dialect.default_schema_name = schema
            command.upgrade(migration_config(connection), "head")
            try:
                yield connection
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def test_migration_round_trip(database_connection: Connection) -> None:
    config = migration_config(database_connection)
    expected = {
        "alembic_version",
        "users",
        "auth_credentials",
        "auth_identities",
        "auth_sessions",
        "auth_one_time_tokens",
    }
    assert set(inspect(database_connection).get_table_names()) == expected
    command.check(config)
    command.downgrade(config, "0001_enable_vector")
    assert inspect(database_connection).get_table_names() == ["alembic_version"]
    command.upgrade(config, "head")
    assert set(inspect(database_connection).get_table_names()) == expected
    command.check(config)


@pytest.mark.parametrize("address", [None, "192.0.2.1", "2001:db8::1"])
def test_session_repository(database_connection: Connection, address: str | None) -> None:
    now = datetime.now(UTC)
    with Session(database_connection, join_transaction_mode="create_savepoint") as database:
        user = UserModel(email="session@example.com")
        other_user = UserModel(email="other@example.com")
        database.add_all([user, other_user])
        database.flush()
        session = AuthSession(
            id=uuid4(),
            user_id=user.id,
            token_hash="a" * 64,
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(days=30),
            user_agent="persistence-test",
            ip_address=ip_address(address) if address is not None else None,
        )
        repository: SessionRepository = SqlAlchemySessionRepository(database)
        repository.create(session)
        second = replace(session, id=uuid4(), token_hash="b" * 64)
        other = replace(session, id=uuid4(), user_id=other_user.id, token_hash="c" * 64)
        expired = replace(
            session,
            id=uuid4(),
            token_hash="d" * 64,
            created_at=now - timedelta(days=2),
            last_seen_at=now - timedelta(days=2),
            expires_at=now - timedelta(days=1),
        )
        for item in (second, other, expired):
            repository.create(item)
        database.commit()
        database.expire_all()
        assert repository.get_by_token_hash(session.token_hash) == session
        assert repository.get_by_token_hash("e" * 64) is None
        stored_expired = repository.get_by_token_hash(expired.token_hash)
        assert stored_expired is not None
        with pytest.raises(InvalidSession):
            stored_expired.require_active(now)
        repository.revoke(session.id)
        revoked = repository.get_by_token_hash(session.token_hash)
        assert revoked is not None and revoked.revoked_at is not None
        with pytest.raises(InvalidSession):
            revoked.require_active(datetime.now(UTC))
        repository.revoke(session.id)
        assert repository.get_by_token_hash(session.token_hash) == revoked
        repository.revoke(uuid4())
        cached_row = database.get(SessionModel, second.id)
        assert cached_row is not None and cached_row.revoked_at is None
        database.execute(
            update(SessionModel)
            .where(SessionModel.id == second.id)
            .values(revoked_at=now)
            .execution_options(synchronize_session=False)
        )
        assert cached_row.revoked_at is None
        refreshed = repository.get_by_token_hash(second.token_hash)
        assert refreshed is not None and refreshed.revoked_at == now
        repository.revoke_all_for_user(user.id)
        assert repository.get_by_token_hash(second.token_hash) == refreshed
        for item in (second, expired):
            stored = repository.get_by_token_hash(item.token_hash)
            assert stored is not None and stored.revoked_at is not None
        assert repository.get_by_token_hash(other.token_hash) == other
        database.commit()
        database.expire_all()
        assert repository.get_by_token_hash(session.token_hash) == revoked
        database.delete(user)
        database.flush()
        assert repository.get_by_token_hash(session.token_hash) is None
        assert repository.get_by_token_hash(other.token_hash) == other


def test_database_constraints_and_cascades(database_connection: Connection) -> None:
    now = datetime.now(UTC)
    user_id, other_user_id = uuid4(), uuid4()
    with Session(database_connection, join_transaction_mode="create_savepoint") as database:
        database.add_all(
            [
                UserModel(id=user_id, email="Owner@Example.com"),
                UserModel(id=other_user_id, email="other@example.com"),
            ]
        )
        database.flush()
        user = database.get(UserModel, user_id)
        assert user is not None and user.status == "active" and user.email_verified_at is None
        assert user.created_at.utcoffset() is not None
        session_values = {
            "user_id": user_id,
            "token_hash": "a" * 64,
            "created_at": now,
            "expires_at": now + timedelta(days=30),
        }
        token_values = {
            "user_id": user_id,
            "token_type": "email_verification",
            "token_hash": "b" * 64,
            "created_at": now,
            "expires_at": now + timedelta(hours=1),
        }
        database.execute(insert(SessionModel).values(**session_values))
        database.execute(insert(OneTimeTokenModel).values(**token_values))
        database.add(IdentityModel(user_id=user_id, provider="google", provider_subject="subject"))
        database.add(
            CredentialModel(
                user_id=user_id, password_hash=PasswordHash.recommended().hash("test-password")
            )
        )
        database.flush()
        invalid_inserts = [
            insert(UserModel).values(email="owner@example.com"),
            insert(UserModel).values(email="invalid@example.com", status="unknown"),
            insert(SessionModel).values(**session_values),
            insert(SessionModel).values(**(session_values | {"token_hash": "raw-token"})),
            insert(SessionModel).values(
                **(session_values | {"token_hash": "c" * 64, "user_id": uuid4()})
            ),
            insert(SessionModel).values(
                **(session_values | {"token_hash": "c" * 64, "expires_at": now})
            ),
            insert(OneTimeTokenModel).values(**token_values),
            insert(OneTimeTokenModel).values(**(token_values | {"token_hash": "raw-token"})),
            insert(OneTimeTokenModel).values(
                **(token_values | {"token_hash": "c" * 64, "token_type": "unknown"})
            ),
            insert(IdentityModel).values(
                user_id=other_user_id, provider="google", provider_subject="subject"
            ),
        ]
        for statement in invalid_inserts:
            with pytest.raises(IntegrityError), database.begin_nested():
                database.execute(statement)
        database.delete(user)
        database.flush()
        for model in (CredentialModel, IdentityModel, OneTimeTokenModel, SessionModel):
            assert database.scalar(select(func.count()).select_from(model)) == 0
