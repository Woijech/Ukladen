from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import Connection, insert, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_auth_persistence import database_connection as database_connection
from test_auth_persistence import migration_config

from alembic import command
from app.modules.notes.infrastructure.orm import PageModel
from app.modules.users.infrastructure.orm import UserModel


def test_page_schema_constraints_cascade_and_migration(database_connection: Connection) -> None:
    config = migration_config(database_connection)
    command.check(config)
    now, owner, other, root = datetime.now(UTC), uuid4(), uuid4(), uuid4()
    with Session(database_connection, join_transaction_mode="create_savepoint") as database:
        database.add_all(
            [
                UserModel(id=owner, email="page@example.com"),
                UserModel(id=other, email="other@example.com"),
            ]
        )
        database.flush()
        values = {"id": root, "user_id": owner, "title": "Training"}
        database.execute(insert(PageModel).values(**values))
        child = uuid4()
        database.execute(
            insert(PageModel).values(id=child, user_id=owner, title="Chest", parent_id=root)
        )
        for changes in (
            {"title": " "},
            {"version": 0},
            {"content": "x" * 100001},
            {"trashed_at": now},
            {"trash_batch_id": uuid4()},
        ):
            with pytest.raises(IntegrityError), database.begin_nested():
                database.execute(insert(PageModel).values(**(values | {"id": uuid4()} | changes)))
        with pytest.raises(IntegrityError), database.begin_nested():
            database.execute(
                insert(PageModel).values(id=uuid4(), user_id=other, parent_id=root, title="Bad")
            )
        with pytest.raises(IntegrityError), database.begin_nested():
            identifier = uuid4()
            database.execute(
                insert(PageModel).values(**(values | {"id": identifier, "parent_id": identifier}))
            )
        user = database.get(UserModel, owner)
        assert user
        database.delete(user)
        database.flush()
        assert database.get(PageModel, root) is None and database.get(PageModel, child) is None
        database.commit()
    command.downgrade(config, "0007_calendar")
    assert "note_pages" not in inspect(database_connection).get_table_names()
    command.upgrade(config, "head")
    command.check(config)
