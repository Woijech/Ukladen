from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import Connection, MetaData, Table, inspect, select, text
from sqlalchemy.orm import Session
from test_auth_persistence import database_connection as database_connection
from test_auth_persistence import migration_config

from alembic import command
from app.modules.calendar.infrastructure.orm import PersonalCalendarEventModel
from app.modules.notes.infrastructure.orm import PageModel
from app.modules.notes.infrastructure.repository import SqlAlchemyPageRepository
from app.modules.relations.infrastructure.orm import CalendarPageLinkModel
from app.modules.users.infrastructure.orm import UserModel


def test_existing_pages_and_links_survive_document_migration(
    database_connection: Connection,
) -> None:
    config = migration_config(database_connection)
    command.downgrade(config, "0009_page_calendar_links")
    old_pages = Table("note_pages", MetaData(), autoload_with=database_connection)
    owner, root, child, event_id, link_id = (uuid4() for _ in range(5))
    now = datetime(2026, 10, 12, 12, tzinfo=UTC)
    content = "# Unparsed\r\n\n[link](https://example.com) <raw> Привет 😀\n"
    with Session(database_connection, join_transaction_mode="create_savepoint") as database:
        database.add(UserModel(id=owner, email="migration@example.com"))
        database.flush()
        database.execute(
            old_pages.insert().values(
                id=root,
                user_id=owner,
                title="Root",
                content=content,
                version=7,
                created_at=now,
                updated_at=now,
                trashed_at=now,
                trash_batch_id=root,
            )
        )
        database.execute(
            old_pages.insert().values(
                id=child,
                user_id=owner,
                parent_id=root,
                title="Empty child",
                content="",
                version=4,
                created_at=now,
                updated_at=now,
                trashed_at=now,
                trash_batch_id=root,
            )
        )
        database.add(
            PersonalCalendarEventModel(
                id=event_id,
                user_id=owner,
                title="Training",
                starts_at=now,
                ends_at=now + timedelta(hours=1),
            )
        )
        database.flush()
        database.add(
            CalendarPageLinkModel(
                id=link_id,
                user_id=owner,
                page_id=root,
                personal_event_id=event_id,
                created_at=now,
            )
        )
        database.commit()
    command.upgrade(config, "head")
    with Session(database_connection, join_transaction_mode="create_savepoint") as database:
        repository = SqlAlchemyPageRepository(database)
        page, nested = repository.get(owner, root), repository.get(owner, child)
        assert page and nested
        assert page.content == content and page.document.blocks[0].id == root
        assert page.version == 7 and page.created_at == page.updated_at == page.trashed_at == now
        assert page.trash_batch_id == root and page.parent_id is None
        assert nested.parent_id == root and nested.document.blocks == () and nested.version == 4
        assert nested.trash_batch_id == root and nested.trashed_at == now
        link = database.get(CalendarPageLinkModel, link_id)
        assert link and link.page_id == root and link.personal_event_id == event_id
    command.check(config)
    command.downgrade(config, "0009_page_calendar_links")
    rows = database_connection.execute(select(old_pages.c.id, old_pages.c.content)).all()
    assert dict(rows) == {root: content, child: ""}
    command.upgrade(config, "head")
    with Session(database_connection, join_transaction_mode="create_savepoint") as database:
        page = SqlAlchemyPageRepository(database).get(owner, root)
        assert page and page.content == content and page.document.blocks[0].id == root
        assert database.get(CalendarPageLinkModel, link_id) is not None
    command.check(config)


@pytest.mark.parametrize("kind", ["heading", "custom_markdown_id", "empty_markdown_block"])
def test_document_downgrade_refuses_loss_before_changing_schema(
    database_connection: Connection,
    kind: str,
) -> None:
    owner, page_id = uuid4(), uuid4()
    block = {"id": str(page_id), "type": "text", "text_format": "markdown", "text": "Keep"}
    if kind == "heading":
        block = {"id": str(page_id), "type": "heading", "text": "Keep", "level": 1}
    elif kind == "custom_markdown_id":
        block["id"] = str(uuid4())
    else:
        block["text"] = ""
    document = {"schema_version": 1, "blocks": [block]}
    with Session(database_connection, join_transaction_mode="create_savepoint") as database:
        database.add(UserModel(id=owner, email="downgrade@example.com"))
        database.flush()
        database.add(PageModel(id=page_id, user_id=owner, title="Keep", document=document))
        database.commit()
    head = database_connection.scalar(text("SELECT version_num FROM alembic_version"))
    with (
        pytest.raises(RuntimeError, match="without losing block structure or IDs"),
        database_connection.begin_nested(),
    ):
        command.downgrade(migration_config(database_connection), "0009_page_calendar_links")
    columns = {column["name"] for column in inspect(database_connection).get_columns("note_pages")}
    assert "document" in columns and "content" not in columns
    assert database_connection.scalar(text("SELECT version_num FROM alembic_version")) == head
    assert database_connection.scalar(
        select(PageModel.document).where(PageModel.id == page_id)
    ) == (document)
