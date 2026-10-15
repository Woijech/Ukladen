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
from app.modules.workspace.infrastructure.orm import (
    DatabaseModel,
    DatabasePropertyModel,
    DatabaseRecordModel,
)


def test_content_owner_constraints_and_preserving_migration(
    database_connection: Connection,
) -> None:
    config = migration_config(database_connection)
    command.check(config)
    owner, other, database_id, foreign_database, page, foreign_page, property_id, record_id = (
        uuid4() for _ in range(8)
    )
    with Session(database_connection, join_transaction_mode="create_savepoint") as session:
        session.add_all(
            [
                UserModel(id=owner, email="records@example.com"),
                UserModel(id=other, email="other-records@example.com"),
            ]
        )
        session.flush()
        session.add_all(
            [
                DatabaseModel(id=database_id, user_id=owner, name="Owned"),
                DatabaseModel(id=foreign_database, user_id=other, name="Foreign"),
                PageModel(id=page, user_id=owner, title="Owned page"),
                PageModel(id=foreign_page, user_id=other, title="Foreign page"),
            ]
        )
        session.flush()
        property_values = {
            "id": property_id,
            "user_id": owner,
            "database_id": database_id,
            "name": "Field",
            "kind": "text",
        }
        session.execute(insert(DatabasePropertyModel).values(**property_values))
        for changes in (
            {"database_id": foreign_database},
            {"user_id": other},
            {"kind": "formula"},
            {"name": " "},
            {"position": -1},
            {"version": 0},
            {"options": {}},
            {"options": [{}] * 101},
        ):
            with pytest.raises(IntegrityError), session.begin_nested():
                session.execute(
                    insert(DatabasePropertyModel).values(
                        **(property_values | {"id": uuid4()} | changes)
                    )
                )
        values = {
            "id": record_id,
            "user_id": owner,
            "database_id": database_id,
            "page_id": page,
            "values": {str(property_id): "Retained"},
        }
        session.execute(insert(DatabaseRecordModel).values(**values))
        with pytest.raises(IntegrityError), session.begin_nested():
            session.execute(insert(DatabaseRecordModel).values(**(values | {"id": uuid4()})))
        available_page = uuid4()
        session.add(PageModel(id=available_page, user_id=owner, title="Constraint target"))
        session.flush()
        for changes in (
            {"database_id": foreign_database},
            {"user_id": other},
            {"page_id": foreign_page},
            {"values": []},
            {"values": {"large": "x" * 131073}},
            {"version": 0},
        ):
            with pytest.raises(IntegrityError), session.begin_nested():
                session.execute(
                    insert(DatabaseRecordModel).values(
                        **(values | {"id": uuid4(), "page_id": available_page} | changes)
                    )
                )
        session.commit()
    with pytest.raises(RuntimeError, match="must be preserved"):
        command.downgrade(config, "0014_user_databases")
    assert database_connection.scalar(
        select(DatabaseRecordModel.values).where(DatabaseRecordModel.id == record_id)
    ) == {str(property_id): "Retained"}
    database_connection.execute(delete(DatabaseModel).where(DatabaseModel.id == database_id))
    assert database_connection.scalar(select(DatabaseRecordModel.id)) is None
    assert database_connection.scalar(select(DatabasePropertyModel.id)) is None
    assert database_connection.scalar(select(PageModel.id).where(PageModel.id == page)) == page
    command.downgrade(config, "0014_user_databases")
    assert "workspace_database_records" not in inspect(database_connection).get_table_names()
    assert database_connection.scalar(select(PageModel.id).where(PageModel.id == page)) == page
    command.upgrade(config, "head")
    command.check(config)
