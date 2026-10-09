from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import Connection, Engine, delete, insert, inspect, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_auth_persistence import database_connection as database_connection
from test_auth_persistence import migration_config
from test_auth_sessions import concurrent_engine as concurrent_engine

from alembic import command
from app.modules.calendar.application.ports import PersonalCalendarEventRepository
from app.modules.calendar.domain.events import PersonalCalendarEvent
from app.modules.calendar.infrastructure.orm import PersonalCalendarEventModel
from app.modules.calendar.infrastructure.repository import SqlAlchemyPersonalCalendarEventRepository
from app.modules.users.infrastructure.orm import UserModel

NOW = datetime(2026, 10, 9, 8, tzinfo=UTC)


def event_for(user_id: UUID, **changes: object) -> PersonalCalendarEvent:
    event = PersonalCalendarEvent(
        id=uuid4(),
        user_id=user_id,
        title="Study session",
        description="Prepare for the next class.",
        starts_at=NOW,
        ends_at=NOW + timedelta(hours=1),
        is_busy=True,
        created_at=NOW - timedelta(days=1),
        updated_at=NOW - timedelta(days=1),
    )
    return replace(event, **changes)


def test_migration_round_trip_preserves_existing_users(database_connection: Connection) -> None:
    config = migration_config(database_connection)
    command.downgrade(config, "0005_academics_profile")
    user_id = uuid4()
    database_connection.execute(
        insert(UserModel).values(
            id=user_id, email="calendar-migration@example.com", display_name="Existing user"
        )
    )
    before = list(database_connection.execute(select(UserModel.__table__)).mappings())
    command.upgrade(config, "head")
    command.check(config)
    assert "personal_calendar_events" in inspect(database_connection).get_table_names()
    with Session(database_connection, join_transaction_mode="create_savepoint") as session:
        event = event_for(user_id)
        repository: PersonalCalendarEventRepository = SqlAlchemyPersonalCalendarEventRepository(
            session
        )
        assert repository.create(user_id, event) == event
        session.commit()
    command.downgrade(config, "0005_academics_profile")
    assert "personal_calendar_events" not in inspect(database_connection).get_table_names()
    assert list(database_connection.execute(select(UserModel.__table__)).mappings()) == before
    command.upgrade(config, "head")
    command.check(config)


def test_owner_scoped_crud_persists_between_sessions(concurrent_engine: Engine) -> None:
    owner_id, other_id = uuid4(), uuid4()
    event = event_for(owner_id)
    other_event = event_for(other_id)
    with Session(concurrent_engine) as session, session.begin():
        session.add_all(
            [
                UserModel(id=owner_id, email="calendar-owner@example.com"),
                UserModel(id=other_id, email="calendar-other@example.com"),
            ]
        )
        session.flush()
        repository = SqlAlchemyPersonalCalendarEventRepository(session)
        assert repository.create(owner_id, event) == event
        repository.create(other_id, other_event)
    with Session(concurrent_engine) as session, session.begin():
        repository = SqlAlchemyPersonalCalendarEventRepository(session)
        assert repository.get(owner_id, event.id) == event
        assert repository.get(other_id, event.id) is None
        assert repository.get(owner_id, uuid4()) is None
        assert repository.list_for_period(other_id, NOW, NOW + timedelta(hours=1)) == [other_event]
        assert repository.update(other_id, replace(event, user_id=other_id)) is None
        assert not repository.delete(other_id, event.id)
        assert repository.update(owner_id, replace(event, id=uuid4())) is None
        changed = repository.update(
            owner_id,
            replace(
                event,
                title="Updated study session",
                description=None,
                starts_at=NOW + timedelta(hours=2),
                ends_at=NOW + timedelta(hours=3),
                is_busy=False,
                created_at=NOW,
            ),
        )
        assert changed is not None
        assert changed.created_at == event.created_at
        assert changed.updated_at > event.updated_at
        assert changed.title == "Updated study session" and changed.description is None
        assert not changed.is_busy and changed.starts_at == NOW + timedelta(hours=2)
    with Session(concurrent_engine) as session, session.begin():
        repository = SqlAlchemyPersonalCalendarEventRepository(session)
        assert repository.get(owner_id, event.id) == changed
        assert repository.delete(owner_id, event.id)
        assert not repository.delete(owner_id, event.id)
        assert not repository.delete(owner_id, uuid4())
        assert repository.get(other_id, other_event.id) == other_event
    with Session(concurrent_engine) as session:
        assert SqlAlchemyPersonalCalendarEventRepository(session).get(owner_id, event.id) is None


def test_period_selection_overlaps_boundaries_timezone_and_order(
    database_connection: Connection,
) -> None:
    owner_id, other_id = uuid4(), uuid4()
    with Session(database_connection, join_transaction_mode="create_savepoint") as session:
        session.add_all(
            [
                UserModel(id=owner_id, email="calendar-period@example.com"),
                UserModel(id=other_id, email="calendar-period-other@example.com"),
            ]
        )
        session.flush()
        repository = SqlAlchemyPersonalCalendarEventRepository(session)
        spanning = event_for(
            owner_id, starts_at=NOW - timedelta(hours=1), ends_at=NOW + timedelta(hours=3)
        )
        tied_first = event_for(owner_id, id=UUID(int=1))
        tied_second = event_for(owner_id, id=UUID(int=2), is_busy=False)
        tail = event_for(
            owner_id, starts_at=NOW + timedelta(hours=1), ends_at=NOW + timedelta(hours=3)
        )
        boundary_before = event_for(owner_id, starts_at=NOW - timedelta(hours=1), ends_at=NOW)
        boundary_after = event_for(
            owner_id, starts_at=NOW + timedelta(hours=2), ends_at=NOW + timedelta(hours=3)
        )
        for event in (
            tied_second,
            boundary_before,
            spanning,
            boundary_after,
            tail,
            tied_first,
        ):
            repository.create(owner_id, event)
        repository.create(other_id, event_for(other_id))
        local = ZoneInfo("Europe/Minsk")
        assert repository.list_for_period(
            owner_id, NOW.astimezone(local), (NOW + timedelta(hours=2)).astimezone(local)
        ) == [spanning, tied_first, tied_second, tail]


def test_owner_mismatch_and_duplicate_id_cannot_replace_an_event(
    database_connection: Connection,
) -> None:
    owner_id, other_id = uuid4(), uuid4()
    event = event_for(owner_id)
    with Session(database_connection, join_transaction_mode="create_savepoint") as session:
        session.add_all(
            [
                UserModel(id=owner_id, email="calendar-duplicate@example.com"),
                UserModel(id=other_id, email="calendar-duplicate-other@example.com"),
            ]
        )
        session.flush()
        repository = SqlAlchemyPersonalCalendarEventRepository(session)
        repository.create(owner_id, event)
        with pytest.raises(ValueError, match="owner"):
            repository.create(other_id, event)
        with pytest.raises(ValueError, match="owner"):
            repository.update(other_id, event)
        with pytest.raises(IntegrityError), session.begin_nested():
            repository.create(other_id, replace(event, user_id=other_id))
        assert repository.get(owner_id, event.id) == event


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
def test_repository_uses_caller_transactions(concurrent_engine: Engine, operation: str) -> None:
    owner_id = uuid4()
    event = event_for(owner_id)
    with Session(concurrent_engine) as session, session.begin():
        session.add(UserModel(id=owner_id, email="calendar-rollback@example.com"))
        session.flush()
        if operation != "create":
            SqlAlchemyPersonalCalendarEventRepository(session).create(owner_id, event)
    with Session(concurrent_engine) as session:
        repository = SqlAlchemyPersonalCalendarEventRepository(session)
        with pytest.raises(RuntimeError), session.begin():
            if operation == "create":
                repository.create(owner_id, event)
            elif operation == "update":
                repository.update(owner_id, replace(event, title="Uncommitted title"))
            else:
                repository.delete(owner_id, event.id)
            raise RuntimeError("Roll back caller transaction.")
    with Session(concurrent_engine) as session:
        stored = SqlAlchemyPersonalCalendarEventRepository(session).get(owner_id, event.id)
        assert stored == (None if operation == "create" else event)


def test_reads_refresh_cached_rows_after_external_update(concurrent_engine: Engine) -> None:
    owner_id = uuid4()
    event = event_for(owner_id)
    with Session(concurrent_engine) as session, session.begin():
        session.add(UserModel(id=owner_id, email="calendar-refresh@example.com"))
        session.flush()
        SqlAlchemyPersonalCalendarEventRepository(session).create(owner_id, event)
    with Session(concurrent_engine, expire_on_commit=False) as reader:
        repository = SqlAlchemyPersonalCalendarEventRepository(reader)
        cached = reader.get(PersonalCalendarEventModel, event.id)
        assert cached is not None
        reader.commit()
        with Session(concurrent_engine) as writer, writer.begin():
            changed = SqlAlchemyPersonalCalendarEventRepository(writer).update(
                owner_id, replace(event, title="Changed externally")
            )
        assert cached.title == event.title
        assert repository.get(owner_id, event.id) == changed
        reader.commit()
        with Session(concurrent_engine) as writer, writer.begin():
            changed = SqlAlchemyPersonalCalendarEventRepository(writer).update(
                owner_id, replace(event, title="Changed again")
            )
        assert repository.list_for_period(owner_id, NOW, event.ends_at) == [changed]


@pytest.mark.parametrize(
    "changes",
    [
        {"title": ""},
        {"title": " \t\n"},
        {"title": None},
        {"starts_at": NOW + timedelta(hours=1)},
        {"ends_at": NOW - timedelta(seconds=1)},
        {"user_id": uuid4()},
    ],
)
def test_database_constraints(database_connection: Connection, changes: dict[str, object]) -> None:
    owner_id = uuid4()
    event = event_for(owner_id)
    with Session(database_connection, join_transaction_mode="create_savepoint") as session:
        session.add(UserModel(id=owner_id, email="calendar-constraints@example.com"))
        session.flush()
        repository = SqlAlchemyPersonalCalendarEventRepository(session)
        repository.create(owner_id, event)
        with pytest.raises(IntegrityError), session.begin_nested():
            session.execute(
                update(PersonalCalendarEventModel)
                .where(PersonalCalendarEventModel.id == event.id)
                .values(**changes)
            )
        assert repository.get(owner_id, event.id) == event


def test_user_deletion_cascades_only_owned_events(database_connection: Connection) -> None:
    owner_id, other_id = uuid4(), uuid4()
    with Session(database_connection, join_transaction_mode="create_savepoint") as session:
        session.add_all(
            [
                UserModel(id=owner_id, email="calendar-cascade@example.com"),
                UserModel(id=other_id, email="calendar-cascade-other@example.com"),
            ]
        )
        session.flush()
        repository = SqlAlchemyPersonalCalendarEventRepository(session)
        event, other = event_for(owner_id), event_for(other_id)
        repository.create(owner_id, event)
        repository.create(other_id, other)
        session.execute(delete(UserModel).where(UserModel.id == owner_id))
        assert repository.get(owner_id, event.id) is None
        assert repository.get(other_id, other.id) == other
