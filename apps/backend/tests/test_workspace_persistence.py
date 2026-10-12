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
from app.modules.users.infrastructure.orm import UserModel
from app.modules.workspace.infrastructure.orm import MembershipModel, OrganizationModel


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


def test_membership_constraints_cascades_and_migration_preserve_targets(
    database_connection: Connection,
) -> None:
    config = migration_config(database_connection)
    owner, other, group, foreign_group, page, foreign_page, event = (uuid4() for _ in range(7))
    now = datetime.now(UTC)
    with Session(database_connection, join_transaction_mode="create_savepoint") as database:
        database.add_all(
            [
                UserModel(id=owner, email="members@example.com"),
                UserModel(id=other, email="other-members@example.com"),
            ]
        )
        database.flush()
        database.execute(
            insert(OrganizationModel),
            [
                {"id": group, "user_id": owner, "kind": "collection", "name": "Training"},
                {"id": foreign_group, "user_id": other, "kind": "tag", "name": "Private"},
            ],
        )
        database.execute(
            insert(PageModel),
            [
                {"id": page, "user_id": owner, "title": "Training"},
                {"id": foreign_page, "user_id": other, "title": "Private"},
            ],
        )
        database.execute(
            insert(PersonalCalendarEventModel).values(
                id=event,
                user_id=owner,
                title="Training",
                starts_at=now,
                ends_at=now + timedelta(hours=1),
            )
        )
        values = {"user_id": owner, "organization_id": group, "page_id": page}
        database.execute(insert(MembershipModel).values(id=uuid4(), **values))
        for changes in (
            {},
            {"user_id": other},
            {"organization_id": foreign_group},
            {"page_id": foreign_page},
            {"page_id": uuid4()},
            {"page_id": None},
            {"personal_event_id": event},
            {"page_id": None, "personal_event_id": uuid4()},
            {"page_id": None, "official_event_id": uuid4()},
        ):
            with pytest.raises(IntegrityError), database.begin_nested():
                database.execute(insert(MembershipModel).values(id=uuid4(), **(values | changes)))
        database.execute(
            insert(MembershipModel).values(
                id=uuid4(), user_id=owner, organization_id=group, personal_event_id=event
            )
        )
        database.execute(delete(PageModel).where(PageModel.id == page))
        assert len(database.scalars(select(MembershipModel)).all()) == 1
        database.execute(
            delete(PersonalCalendarEventModel).where(PersonalCalendarEventModel.id == event)
        )
        assert database.scalar(select(MembershipModel)) is None
        database.execute(
            insert(MembershipModel).values(
                id=uuid4(), user_id=other, organization_id=foreign_group, page_id=foreign_page
            )
        )
        database.execute(delete(OrganizationModel).where(OrganizationModel.id == foreign_group))
        assert database.scalar(select(MembershipModel)) is None
        assert database.get(PageModel, foreign_page) is not None
        database.execute(
            insert(OrganizationModel).values(
                id=foreign_group, user_id=other, kind="tag", name="Keep"
            )
        )
        database.execute(
            insert(MembershipModel).values(
                id=uuid4(),
                user_id=other,
                organization_id=foreign_group,
                page_id=foreign_page,
            )
        )
        database.commit()
    command.check(config)
    command.downgrade(config, "0011_workspace_organizations")
    assert "workspace_memberships" not in inspect(database_connection).get_table_names()
    assert (
        database_connection.scalar(select(PageModel.id).where(PageModel.id == foreign_page))
        == foreign_page
    )
    command.upgrade(config, "head")
    command.check(config)
