from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import Connection, MetaData, Table, func, insert, inspect, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from test_auth_persistence import database_connection as database_connection
from test_auth_persistence import migration_config
from test_bsuir_academics import group_fixture
from test_schedule_expansion import schedule_fixture

from alembic import command
from app.modules.academics.infrastructure.orm import UniversityGroupModel
from app.modules.calendar.infrastructure.orm import (
    PersonalCalendarEventModel,
    ScheduleOverrideModel,
)
from app.modules.schedule.application.expansion import expand_schedule
from app.modules.schedule.infrastructure.orm import OfficialScheduleEventModel, ScheduleSourceModel
from app.modules.users.infrastructure.orm import UserModel


def test_upgrade_preserves_legacy_event_data(database_connection: Connection) -> None:
    config = migration_config(database_connection)
    command.downgrade(config, "0006_personal_calendar_events")
    legacy = Table("personal_calendar_events", MetaData(), autoload_with=database_connection)
    now, user_id, event_id = datetime.now(UTC), uuid4(), uuid4()
    database_connection.execute(insert(UserModel).values(id=user_id, email="legacy@example.com"))
    values = {
        "id": event_id,
        "user_id": user_id,
        "title": "Existing event",
        "description": "Existing Unicode content: Привет",
        "starts_at": now,
        "ends_at": now + timedelta(hours=1),
        "is_busy": False,
        "created_at": now - timedelta(days=1),
        "updated_at": now,
    }
    database_connection.execute(legacy.insert().values(**values))
    command.upgrade(config, "head")
    command.check(config)
    upgraded = database_connection.execute(select(PersonalCalendarEventModel.__table__)).one()
    for name, value in values.items():
        assert upgraded._mapping["blocks_time" if name == "is_busy" else name] == value
    assert upgraded.version == 1 and upgraded.location is None
    command.downgrade(config, "0006_personal_calendar_events")
    assert dict(database_connection.execute(select(legacy)).one()._mapping) == values
    command.upgrade(config, "head")
    command.check(config)


@pytest.mark.parametrize(
    "changes", [{"title": "x" * 201}, {"title": " Untrimmed "}, {"description": "x" * 10001}]
)
def test_upgrade_rejects_legacy_data_without_truncation(
    database_connection: Connection, changes: dict[str, str]
) -> None:
    config = migration_config(database_connection)
    command.downgrade(config, "0006_personal_calendar_events")
    legacy = Table("personal_calendar_events", MetaData(), autoload_with=database_connection)
    now, user_id = datetime.now(UTC), uuid4()
    database_connection.execute(
        insert(UserModel).values(id=user_id, email="invalid-legacy@example.com")
    )
    database_connection.execute(
        legacy.insert().values(
            **(
                {
                    "id": uuid4(),
                    "user_id": user_id,
                    "title": "Existing event",
                    "starts_at": now,
                    "ends_at": now + timedelta(hours=1),
                }
                | changes
            ),
        )
    )
    before = database_connection.execute(select(legacy)).one()
    with (
        pytest.raises(SQLAlchemyError, match="need validation"),
        database_connection.begin_nested(),
    ):
        command.upgrade(config, "head")
    assert database_connection.execute(select(legacy)).one() == before
    columns = {column["name"] for column in inspect(database_connection).get_columns(legacy.name)}
    assert "is_busy" in columns and "blocks_time" not in columns


def test_calendar_migration_constraints_and_owner_cascade(database_connection: Connection) -> None:
    config = migration_config(database_connection)
    command.downgrade(config, "0006_schedule_storage")
    now, user_id = datetime.now(UTC), uuid4()
    official = expand_schedule(schedule_fixture())[0]
    with Session(database_connection, join_transaction_mode="create_savepoint") as database:
        database.add(UserModel(id=user_id, email="calendar@example.com"))
        database.add(UniversityGroupModel(**asdict(group_fixture())))
        database.flush()
        database.add(ScheduleSourceModel(group_id=24066, group_number="353501", status="ready"))
        database.flush()
        database.add(OfficialScheduleEventModel(**asdict(official)))
        database.commit()
    command.upgrade(config, "head")
    command.check(config)
    personal_values = {
        "id": uuid4(),
        "user_id": user_id,
        "title": "Study",
        "starts_at": now,
        "ends_at": now + timedelta(hours=1),
    }
    override_values = {"user_id": user_id, "official_event_id": official.id}
    with Session(database_connection, join_transaction_mode="create_savepoint") as database:
        database.execute(insert(PersonalCalendarEventModel).values(**personal_values))
        database.execute(insert(ScheduleOverrideModel).values(**override_values))
        invalid = [
            insert(PersonalCalendarEventModel).values(
                **(personal_values | {"id": uuid4(), "title": " "})
            ),
            insert(PersonalCalendarEventModel).values(
                **(personal_values | {"id": uuid4(), "ends_at": now})
            ),
            insert(PersonalCalendarEventModel).values(
                **(personal_values | {"id": uuid4(), "version": 0})
            ),
            insert(ScheduleOverrideModel).values(**override_values),
            insert(ScheduleOverrideModel).values(
                **(override_values | {"official_event_id": uuid4()})
            ),
        ]
        for statement in invalid:
            with pytest.raises(IntegrityError), database.begin_nested():
                database.execute(statement)
        row = database.get(ScheduleOverrideModel, (user_id, official.id))
        assert row is not None and row.version == 1 and not row.hidden and not row.skipped
        for changes in ({"starts_at": now}, {"starts_at": now, "ends_at": now}, {"version": 0}):
            with pytest.raises(IntegrityError), database.begin_nested():
                for name, value in changes.items():
                    setattr(row, name, value)
                database.flush()
        assert database.get(OfficialScheduleEventModel, official.id) is not None
        database.commit()
    command.downgrade(config, "0006_schedule_storage")
    tables = inspect(database_connection).get_table_names()
    assert "schedule_overrides" not in tables and "personal_calendar_events" in tables
    legacy_columns = {
        column["name"]
        for column in inspect(database_connection).get_columns("personal_calendar_events")
    }
    assert "is_busy" in legacy_columns and "blocks_time" not in legacy_columns
    with Session(database_connection, join_transaction_mode="create_savepoint") as database:
        assert database.get(UserModel, user_id) is not None
        assert database.get(OfficialScheduleEventModel, official.id) is not None
        database.commit()
    command.upgrade(config, "head")
    command.check(config)
    with Session(database_connection, join_transaction_mode="create_savepoint") as database:
        database.execute(insert(ScheduleOverrideModel).values(**override_values))
        user = database.get(UserModel, user_id)
        assert user is not None
        database.delete(user)
        database.flush()
        for model in (PersonalCalendarEventModel, ScheduleOverrideModel):
            assert database.scalar(select(func.count()).select_from(model)) == 0
        assert database.get(OfficialScheduleEventModel, official.id) is not None
