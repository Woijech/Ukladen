from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import Connection, delete, insert, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_auth_persistence import database_connection as database_connection
from test_auth_persistence import migration_config

from alembic import command
from app.modules.calendar.infrastructure.orm import PersonalCalendarEventModel
from app.modules.notes.infrastructure.orm import PageModel
from app.modules.relations.infrastructure.orm import CalendarPageLinkModel
from app.modules.users.infrastructure.orm import UserModel


def test_typed_link_constraints_lifecycles_and_migration(database_connection: Connection) -> None:
    config = migration_config(database_connection)
    command.check(config)
    now, owner, other, page_id, event_id = datetime.now(UTC), uuid4(), uuid4(), uuid4(), uuid4()
    with Session(database_connection, join_transaction_mode="create_savepoint") as database:
        database.add_all(
            [
                UserModel(id=owner, email="links@example.com"),
                UserModel(id=other, email="other@example.com"),
            ]
        )
        database.flush()
        database.execute(insert(PageModel).values(id=page_id, user_id=owner, title="T"))
        database.execute(
            insert(PersonalCalendarEventModel).values(
                id=event_id,
                user_id=owner,
                title="T",
                starts_at=now,
                ends_at=now + timedelta(hours=1),
            )
        )
        values = {
            "id": uuid4(),
            "user_id": owner,
            "page_id": page_id,
            "personal_event_id": event_id,
        }
        database.execute(insert(CalendarPageLinkModel).values(**values))
        for changes in (
            {},
            {"user_id": other},
            {"page_id": uuid4()},
            {"personal_event_id": uuid4()},
            {"personal_event_id": None},
            {"official_event_id": uuid4()},
        ):
            with pytest.raises(IntegrityError), database.begin_nested():
                database.execute(
                    insert(CalendarPageLinkModel).values(**(values | {"id": uuid4()} | changes))
                )
        database.execute(
            delete(PersonalCalendarEventModel).where(PersonalCalendarEventModel.id == event_id)
        )
        assert database.scalar(select(CalendarPageLinkModel)) is None
        assert database.get(PageModel, page_id) is not None
        database.commit()
    command.downgrade(config, "0008_note_pages")
    assert "page_calendar_links" not in inspect(database_connection).get_table_names()
    assert (
        database_connection.scalar(select(PageModel.id).where(PageModel.id == page_id)) == page_id
    )
    command.upgrade(config, "head")
    command.check(config)
