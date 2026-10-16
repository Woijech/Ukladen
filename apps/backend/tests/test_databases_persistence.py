from uuid import uuid4

import pytest
from sqlalchemy import Connection, delete, insert, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_auth_persistence import database_connection as database_connection
from test_auth_persistence import migration_config

from alembic import command
from app.modules.notes.infrastructure.orm import PageModel
from app.modules.users.infrastructure.orm import UserModel
from app.modules.workspace.infrastructure.orm import DatabaseModel


def test_database_constraints_and_refused_destructive_downgrade(
    database_connection: Connection,
) -> None:
    config = migration_config(database_connection)
    command.check(config)
    owner, page, identifier = uuid4(), uuid4(), uuid4()
    with Session(database_connection, join_transaction_mode="create_savepoint") as session:
        session.add(UserModel(id=owner, email="database@example.com"))
        session.flush()
        session.add(PageModel(id=page, user_id=owner, title="Preserved"))
        session.execute(insert(DatabaseModel).values(id=identifier, user_id=owner, name="Workouts"))
        for changes in (
            {"name": " "},
            {"color": "#ABCDEF"},
            {"version": 0},
            {"schema_version": 0},
            {"user_id": uuid4()},
        ):
            with pytest.raises(IntegrityError), session.begin_nested():
                session.execute(
                    insert(DatabaseModel).values(
                        **({"id": uuid4(), "user_id": owner, "name": "Valid"} | changes)
                    )
                )
        session.commit()
    with pytest.raises(RuntimeError, match="must be preserved"):
        command.downgrade(config, "0013_saved_calendar_views")
    assert database_connection.scalar(select(DatabaseModel.id)) == identifier
    assert database_connection.scalar(select(PageModel.id)) == page
    database_connection.execute(delete(DatabaseModel))
    command.downgrade(config, "0013_saved_calendar_views")
    assert "workspace_databases" not in inspect(database_connection).get_table_names()
    assert database_connection.scalar(select(PageModel.id)) == page
    command.upgrade(config, "head")
    command.check(config)
