from uuid import uuid4

import pytest
from sqlalchemy import Connection, insert, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_auth_persistence import database_connection as database_connection
from test_auth_persistence import migration_config

from alembic import command
from app.modules.users.infrastructure.orm import UserModel
from app.modules.workspace.infrastructure.orm import OrganizationModel


def test_organization_constraints_cascade_and_migration(database_connection: Connection) -> None:
    config = migration_config(database_connection)
    command.check(config)
    owner, identifier = uuid4(), uuid4()
    with Session(database_connection, join_transaction_mode="create_savepoint") as database:
        database.add(UserModel(id=owner, email="workspace@example.com"))
        database.flush()
        values = {"id": identifier, "user_id": owner, "kind": "collection", "name": "Training"}
        database.execute(insert(OrganizationModel).values(**values))
        for changes in (
            {"kind": "unknown"},
            {"name": " "},
            {"name": " padded "},
            {"color": "#ABCDEF"},
            {"color": "red"},
            {"version": 0},
            {"user_id": uuid4()},
        ):
            with pytest.raises(IntegrityError), database.begin_nested():
                database.execute(
                    insert(OrganizationModel).values(**(values | {"id": uuid4()} | changes))
                )
        user = database.get(UserModel, owner)
        assert user
        database.delete(user)
        database.flush()
        assert database.get(OrganizationModel, identifier) is None
        database.commit()
    command.downgrade(config, "0010_page_block_documents")
    assert "workspace_organizations" not in inspect(database_connection).get_table_names()
    command.upgrade(config, "head")
    command.check(config)
