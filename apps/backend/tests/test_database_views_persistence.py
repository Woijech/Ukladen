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
from app.modules.workspace.infrastructure.orm import DatabaseModel, DatabaseViewModel


def test_view_constraints_and_lossless_migration(database_connection: Connection) -> None:
    config = migration_config(database_connection)
    command.check(config)
    owner, other, database_id, view_id, page_id = (uuid4() for _ in range(5))
    values = {
        "id": view_id,
        "user_id": owner,
        "database_id": database_id,
        "name": "Table",
        "query": {"version": 1},
    }
    with Session(database_connection, join_transaction_mode="create_savepoint") as session:
        session.add_all(
            [
                UserModel(id=owner, email="views-db@example.com"),
                UserModel(id=other, email="foreign-views-db@example.com"),
            ]
        )
        session.flush()
        session.add_all(
            [
                DatabaseModel(id=database_id, user_id=owner, name="Database"),
                PageModel(id=page_id, user_id=owner, title="Preserved"),
            ]
        )
        session.flush()
        session.execute(insert(DatabaseViewModel).values(**values))
        for changes in (
            {"user_id": other},
            {"name": " "},
            {"color": "#ABCDEF"},
            {"layout": "board"},
            {"version": 0},
            {"query": []},
            {"query": {}},
            {"query": {"version": True}},
            {"query": {"version": 1.0}},
            {"query": {"version": 1, "large": "x" * 65537}},
        ):
            with pytest.raises(IntegrityError), session.begin_nested():
                session.execute(
                    insert(DatabaseViewModel).values(**(values | {"id": uuid4()} | changes))
                )
        session.commit()
    with pytest.raises(RuntimeError, match="must be preserved"):
        command.downgrade(config, "0015_database_content")
    assert database_connection.scalar(select(DatabaseViewModel.id)) == view_id
    database_connection.execute(delete(DatabaseViewModel))
    command.downgrade(config, "0015_database_content")
    assert "workspace_database_views" not in inspect(database_connection).get_table_names()
    assert database_connection.scalar(select(PageModel.id)) == page_id
    command.upgrade(config, "head")
    command.check(config)
