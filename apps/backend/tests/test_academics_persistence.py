from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import Connection, Engine, delete, event, insert, inspect, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_academics import GROUP, OTHER
from test_academics import provider as provider
from test_auth_persistence import database_connection as database_connection
from test_auth_persistence import migration_config
from test_auth_sessions import concurrent_engine as concurrent_engine

from alembic import command
from app.modules.academics.application.profile import AcademicService
from app.modules.academics.domain.profile import AcademicProfileConflict
from app.modules.academics.infrastructure.orm import AcademicProfileModel, UniversityGroupModel
from app.modules.academics.infrastructure.repository import SqlAlchemyAcademicProfileRepository
from app.modules.auth.infrastructure.orm import CredentialModel, IdentityModel, SessionModel
from app.modules.auth.infrastructure.token_service import hash_token
from app.modules.users.domain.profile import ProfileUnavailable
from app.modules.users.infrastructure.orm import UserModel
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication


def test_migration_preserves_existing_users(database_connection: Connection) -> None:
    config = migration_config(database_connection)
    command.downgrade(config, "0004_users_avatar")
    ids = [uuid4(), uuid4()]
    for i, user_id in enumerate(ids):
        database_connection.execute(
            insert(UserModel).values(
                id=user_id,
                email=f"existing-{i}@example.com",
                status="active",
                display_name="Existing",
                timezone="Europe/Minsk",
                locale="en",
            )
        )
    database_connection.execute(
        insert(CredentialModel).values(user_id=ids[0], password_hash="unchanged-hash")
    )
    database_connection.execute(
        insert(IdentityModel).values(
            user_id=ids[1], provider="google", provider_subject="unchanged-subject"
        )
    )
    database_connection.execute(
        insert(SessionModel).values(
            user_id=ids[1],
            token_hash=hash_token("test-session"),
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    models = (UserModel, CredentialModel, IdentityModel, SessionModel)
    before = {
        m.__tablename__: list(database_connection.execute(select(m.__table__)).mappings())
        for m in models
    }
    command.upgrade(config, "head")
    command.check(config)
    assert database_connection.execute(select(AcademicProfileModel)).first() is None
    assert database_connection.execute(select(UniversityGroupModel)).first() is None
    with Session(database_connection, join_transaction_mode="create_savepoint") as session:
        repository = SqlAlchemyAcademicProfileRepository(session)
        repository.save(ids[0], GROUP, 1)
        repository.save(ids[1], replace(OTHER, course=None), None)
        session.commit()
    command.downgrade(config, "0004_users_avatar")
    assert "academic_profiles" not in inspect(database_connection).get_table_names()
    after = {
        m.__tablename__: list(database_connection.execute(select(m.__table__)).mappings())
        for m in models
    }
    assert after == before
    command.upgrade(config, "head")
    command.check(config)


def test_repository_ownership_persistence_rollback_and_cascade(concurrent_engine: Engine) -> None:
    with Session(concurrent_engine) as database, database.begin():
        user, other = UserModel(email="academic@example.com"), UserModel(email="other@example.com")
        database.add_all([user, other])
        database.flush()
        ids = user.id, other.id
        repository = SqlAlchemyAcademicProfileRepository(database)
        assert repository.get(user.id) is None
        profile = repository.save(user.id, GROUP, 1)
        repository.save(other.id, OTHER, None)
    with Session(concurrent_engine) as database:
        repository = SqlAlchemyAcademicProfileRepository(database)
        assert repository.get(ids[0]) == profile
        database.rollback()
        with pytest.raises(RuntimeError), database.begin():
            repository.save(ids[0], replace(OTHER, course=None), 2)
            raise RuntimeError("roll back both metadata and profile")
        assert repository.get(ids[0]) == profile
        other = repository.get(ids[1])
        assert other is not None and other.group == OTHER
        database.rollback()
        with database.begin():
            updated = repository.save(ids[0], GROUP, None)
            assert (
                updated.created_at == profile.created_at
                and updated.updated_at >= profile.updated_at
            )
        with database.begin():
            database.execute(delete(UserModel).where(UserModel.id == ids[0]))
        assert repository.get(ids[0]) is None
        assert repository.get(ids[1]) is not None


@pytest.mark.parametrize("failure", ["write", "commit"])
def test_database_failure_rolls_back_all_records(concurrent_engine: Engine, failure: str) -> None:
    with Session(concurrent_engine) as database, database.begin():
        user = UserModel(email="rollback@example.com")
        database.add(user)
        database.flush()
        user_id = user.id
    with Session(concurrent_engine) as database:
        repository = SqlAlchemyAcademicProfileRepository(database)
        if failure == "commit":

            def fail_commit(session: Session) -> None:
                raise RuntimeError("commit failed")

            event.listen(database, "before_commit", fail_commit)
        with pytest.raises((RuntimeError, IntegrityError)), database.begin():
            repository.save(user_id, GROUP, -1 if failure == "write" else 1)
    with Session(concurrent_engine) as database:
        assert database.get(AcademicProfileModel, user_id) is None
        assert database.get(UniversityGroupModel, GROUP.id) is None


@pytest.mark.parametrize("status", ["disabled", "missing"])
def test_service_rechecks_canonical_user(concurrent_engine: Engine, provider, status: str) -> None:
    with Session(concurrent_engine) as database, database.begin():
        user = UserModel(email="eligible@example.com")
        database.add(user)
        database.flush()
        user_id = user.id
        SqlAlchemyAcademicProfileRepository(database).save(user_id, GROUP, 1)
    with Session(concurrent_engine) as database:
        service = AcademicService(
            SqlAlchemyAcademicProfileRepository(database),
            SqlAlchemyUserAuthentication(database),
            provider,
        )
        with database.begin():
            profile = service.get(user_id)
        prepared = service.prepare(profile, {"subgroup": 2})
        with Session(concurrent_engine) as writer, writer.begin():
            if status == "missing":
                writer.execute(delete(UserModel).where(UserModel.id == user_id))
            else:
                writer.execute(
                    update(UserModel).where(UserModel.id == user_id).values(status="disabled")
                )
        with pytest.raises(ProfileUnavailable), database.begin():
            service.update(user_id, prepared)
        with pytest.raises(ProfileUnavailable), database.begin():
            service.get(user_id)


def test_subgroup_update_detects_group_changed_in_another_session(
    concurrent_engine: Engine, provider
) -> None:
    with Session(concurrent_engine) as database, database.begin():
        user = UserModel(email="concurrent@example.com")
        database.add(user)
        database.flush()
        user_id = user.id
        SqlAlchemyAcademicProfileRepository(database).save(user_id, GROUP, 1)
    with Session(concurrent_engine) as database:
        service = AcademicService(
            SqlAlchemyAcademicProfileRepository(database),
            SqlAlchemyUserAuthentication(database),
            provider,
        )
        with database.begin():
            profile = service.get(user_id)
        prepared = service.prepare(profile, {"subgroup": 2})
        with Session(concurrent_engine) as writer, writer.begin():
            SqlAlchemyAcademicProfileRepository(writer).save(user_id, OTHER, None)
        with pytest.raises(AcademicProfileConflict), database.begin():
            service.update(user_id, prepared)
        current = service.get(user_id)
        assert current is not None and current.group == OTHER
