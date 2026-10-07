from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import Connection, func, insert, inspect, select
from sqlalchemy.exc import IntegrityError
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
    assert "schedule_overrides" not in tables and "personal_calendar_events" not in tables
    with Session(database_connection, join_transaction_mode="create_savepoint") as database:
        assert database.get(UserModel, user_id) is not None
        assert database.get(OfficialScheduleEventModel, official.id) is not None
        database.commit()
    command.upgrade(config, "head")
    command.check(config)
    with Session(database_connection, join_transaction_mode="create_savepoint") as database:
        database.execute(insert(PersonalCalendarEventModel).values(**personal_values))
        database.execute(insert(ScheduleOverrideModel).values(**override_values))
        user = database.get(UserModel, user_id)
        assert user is not None
        database.delete(user)
        database.flush()
        for model in (PersonalCalendarEventModel, ScheduleOverrideModel):
            assert database.scalar(select(func.count()).select_from(model)) == 0
        assert database.get(OfficialScheduleEventModel, official.id) is not None
