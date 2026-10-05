from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import UTC, datetime, timedelta
from threading import Event
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, Engine, insert, text, update
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session
from test_auth_persistence import database_connection as database_connection
from test_auth_persistence import migration_config
from test_auth_sessions import concurrent_engine as concurrent_engine

from alembic import command
from app.modules.auth.infrastructure.orm import (
    CredentialModel,
    IdentityModel,
    OneTimeTokenModel,
    SessionModel,
)
from app.modules.users.application.profile import ProfileService
from app.modules.users.domain.profile import ProfileUnavailable
from app.modules.users.infrastructure.orm import UserModel
from app.modules.users.infrastructure.repository import (
    SqlAlchemyProfileRepository,
    SqlAlchemyUserRegistration,
)


def test_migration_preserves_existing_password_and_google_accounts(
    database_connection: Connection,
) -> None:
    config = migration_config(database_connection)
    command.downgrade(config, "0002_auth_persistence")
    now = datetime.now(UTC)
    ids = [uuid4(), uuid4()]
    for user_id, email in zip(ids, ("password@example.com", "google@example.com"), strict=True):
        database_connection.execute(
            text("INSERT INTO users (id, email) VALUES (:id, :email)"),
            {"id": user_id, "email": email},
        )
    database_connection.execute(
        insert(CredentialModel).values(user_id=ids[0], password_hash="preserved-hash")
    )
    database_connection.execute(
        insert(IdentityModel).values(
            user_id=ids[1], provider="google", provider_subject="preserved-subject"
        )
    )
    database_connection.execute(
        insert(SessionModel).values(
            user_id=ids[0], token_hash="a" * 64, expires_at=now + timedelta(days=1)
        )
    )
    database_connection.execute(
        insert(OneTimeTokenModel).values(
            user_id=ids[0],
            token_type="email_verification",
            token_hash="b" * 64,
            expires_at=now + timedelta(hours=1),
        )
    )

    def stored_auth() -> dict[str, list[dict[str, object]]]:
        return {
            table: [
                dict(row)
                for row in database_connection.execute(
                    text(f"SELECT * FROM {table} ORDER BY 1")
                ).mappings()
            ]
            for table in (
                "users",
                "auth_credentials",
                "auth_identities",
                "auth_sessions",
                "auth_one_time_tokens",
            )
        }

    before = stored_auth()
    command.upgrade(config, "head")
    command.check(config)
    with Session(database_connection, join_transaction_mode="create_savepoint") as database:
        for user_id in ids:
            profile = ProfileService(SqlAlchemyProfileRepository(database)).get(user_id)
            assert (profile.display_name, profile.timezone, profile.locale) == (None, "UTC", "ru")
            original = next(row for row in before["users"] if row["id"] == user_id)
            assert (
                profile.created_at == original["created_at"]
                and profile.updated_at == original["updated_at"]
            )
        # The existing registration port needs no new input after upgrade.
        new_id = SqlAlchemyUserRegistration(database).create("new@example.com")
        profile = ProfileService(SqlAlchemyProfileRepository(database)).get(new_id)
        assert (profile.display_name, profile.timezone, profile.locale) == (None, "UTC", "ru")
        database.rollback()
    command.downgrade(config, "0002_auth_persistence")
    assert stored_auth() == before
    command.upgrade(config, "head")
    command.check(config)
    after = stored_auth()
    after["users"] = [
        {
            k: v
            for k, v in row.items()
            if k not in {"display_name", "timezone", "locale", "avatar_key"}
        }
        for row in after["users"]
    ]
    assert after == before


@pytest.mark.parametrize(
    "changes",
    [
        {"display_name": ""},
        {"display_name": " "},
        {"display_name": " Alex"},
        {"display_name": "Alex\t"},
        {"display_name": "x" * 101},
        {"timezone": ""},
        {"timezone": None},
        {"locale": "fr"},
        {"locale": None},
    ],
)
def test_profile_database_constraints(
    database_connection: Connection, changes: dict[str, object]
) -> None:
    with Session(database_connection, join_transaction_mode="create_savepoint") as database:
        user = UserModel(email="constraints@example.com")
        database.add(user)
        database.flush()
        before = SqlAlchemyProfileRepository(database).get_active(user.id)
        with pytest.raises((DataError, IntegrityError)), database.begin_nested():
            database.execute(update(UserModel).where(UserModel.id == user.id).values(**changes))
        assert SqlAlchemyProfileRepository(database).get_active(user.id) == before


def test_repository_rechecks_canonical_status_and_refreshes_reads(
    concurrent_engine: Engine,
) -> None:
    with Session(concurrent_engine) as database, database.begin():
        user_id = SqlAlchemyUserRegistration(database).create("canonical@example.com")
    with Session(concurrent_engine, expire_on_commit=False) as reader:
        repository = SqlAlchemyProfileRepository(reader)
        before = repository.get_active(user_id)
        reader.commit()
        with Session(concurrent_engine) as writer, writer.begin():
            ProfileService(SqlAlchemyProfileRepository(writer)).update(user_id, {"locale": "en"})
        assert repository.get_active(user_id) != before
        reader.commit()
        with Session(concurrent_engine) as writer, writer.begin():
            writer.execute(
                update(UserModel).where(UserModel.id == user_id).values(status="disabled")
            )
        for target in (user_id, uuid4()):
            service = ProfileService(repository)
            with pytest.raises(ProfileUnavailable):
                service.get(target)
            with pytest.raises(ProfileUnavailable):
                service.update(target, {"locale": "ru"})


@pytest.mark.parametrize("first_outcome", ["commit", "rollback", "disable"])
def test_concurrent_partial_updates_preserve_unrelated_fields(
    concurrent_engine: Engine, first_outcome: str
) -> None:
    with Session(concurrent_engine) as database, database.begin():
        user_id = SqlAlchemyUserRegistration(database).create("concurrent@example.com")
    attempted = Event()

    def second_update(target: UUID) -> None:
        with Session(concurrent_engine) as database, database.begin():
            attempted.set()
            ProfileService(SqlAlchemyProfileRepository(database)).update(target, {"locale": "en"})

    with Session(concurrent_engine) as first, ThreadPoolExecutor(max_workers=1) as executor:
        ProfileService(SqlAlchemyProfileRepository(first)).update(
            user_id, {"display_name": "Alex", "timezone": "Europe/Minsk"}
        )
        if first_outcome == "disable":
            first.execute(
                update(UserModel).where(UserModel.id == user_id).values(status="disabled")
            )
        future = executor.submit(second_update, user_id)
        assert attempted.wait(1)
        try:
            with pytest.raises(TimeoutError):
                future.result(timeout=0.1)
        finally:
            first.rollback() if first_outcome == "rollback" else first.commit()
        if first_outcome == "disable":
            with pytest.raises(ProfileUnavailable):
                future.result(timeout=3)
        else:
            future.result(timeout=3)
    with Session(concurrent_engine) as database:
        user = database.get(UserModel, user_id)
        assert user
        if first_outcome == "rollback":
            assert (user.display_name, user.timezone, user.locale) == (None, "UTC", "en")
        else:
            assert (user.display_name, user.timezone, user.locale) == (
                "Alex",
                "Europe/Minsk",
                "ru" if first_outcome == "disable" else "en",
            )
