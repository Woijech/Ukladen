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
from app.modules.workspace.infrastructure.orm import CalendarViewModel, OrganizationModel


def test_view_constraints_owner_cascade_and_preserving_migration(
    database_connection: Connection,
) -> None:
    config = migration_config(database_connection)
    command.check(config)
    owner, page, collection = uuid4(), uuid4(), uuid4()
    values = {
        "user_id": owner,
        "name": "Study",
        "sources": [{"source": "personal", "collection_ids": [str(collection)], "tag_ids": []}],
    }
    with Session(database_connection, join_transaction_mode="create_savepoint") as database:
        database.add(UserModel(id=owner, email="views@example.com"))
        database.flush()
        database.add_all(
            [
                PageModel(id=page, user_id=owner, title="Page"),
                OrganizationModel(id=collection, user_id=owner, kind="collection", name="Study"),
            ]
        )
        database.flush()
        database.execute(insert(CalendarViewModel).values(id=uuid4(), **values))
        for changes in (
            {"name": " "},
            {"name": " padded "},
            {"color": "#ABCDEF"},
            {"version": 0},
            {"layout": "board"},
            {"sort_order": "bad"},
            {"sources": []},
            {"sources": {}},
            {"sources": [{}, {}, {}]},
            {"user_id": uuid4()},
        ):
            with pytest.raises(IntegrityError), database.begin_nested():
                database.execute(insert(CalendarViewModel).values(id=uuid4(), **(values | changes)))
        database.commit()
    command.downgrade(config, "0012_workspace_memberships")
    assert "workspace_calendar_views" not in inspect(database_connection).get_table_names()
    assert database_connection.scalar(select(PageModel.id).where(PageModel.id == page)) == page
    assert (
        database_connection.scalar(
            select(OrganizationModel.id).where(OrganizationModel.id == collection)
        )
        == collection
    )
    command.upgrade(config, "head")
    command.check(config)
    with Session(database_connection, join_transaction_mode="create_savepoint") as database:
        database.execute(insert(CalendarViewModel).values(id=uuid4(), **values))
        database.execute(delete(UserModel).where(UserModel.id == owner))
        assert database.scalar(select(CalendarViewModel.id)) is None
        database.commit()
