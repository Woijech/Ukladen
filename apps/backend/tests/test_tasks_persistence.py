from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import Connection, Engine, delete, insert, inspect, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_auth_persistence import database_connection as database_connection
from test_auth_persistence import migration_config
from test_auth_sessions import concurrent_engine as concurrent_engine

from alembic import command
from app.modules.tasks.application.ports import TaskRepository
from app.modules.tasks.domain.tasks import Task, TaskVersionConflict
from app.modules.tasks.infrastructure.orm import TaskModel
from app.modules.tasks.infrastructure.repository import SqlAlchemyTaskRepository
from app.modules.users.infrastructure.orm import UserModel


def test_migration_preserves_users_and_refuses_data_loss(database_connection: Connection) -> None:
    config = migration_config(database_connection)
    command.downgrade(config, "0021_google_email_confirmations")
    owner = uuid4()
    database_connection.execute(
        insert(UserModel).values(id=owner, email="task-migration@example.com")
    )
    before = list(database_connection.execute(select(UserModel.__table__)).mappings())
    command.upgrade(config, "head")
    command.check(config)
    database_connection.execute(
        insert(TaskModel).values(id=uuid4(), user_id=owner, title="Keep me")
    )
    with pytest.raises(RuntimeError, match="populated task storage"):
        command.downgrade(config, "0021_google_email_confirmations")
    assert database_connection.scalar(select(TaskModel.title)) == "Keep me"
    database_connection.execute(delete(TaskModel))
    command.downgrade(config, "0021_google_email_confirmations")
    assert "tasks" not in inspect(database_connection).get_table_names()
    assert list(database_connection.execute(select(UserModel.__table__)).mappings()) == before
    command.upgrade(config, "head")
    command.check(config)


def test_repository_owner_version_filters_and_cascade(database_connection: Connection) -> None:
    owner, other, identifier = uuid4(), uuid4(), uuid4()
    now = datetime.now(UTC)
    task = Task(
        id=identifier,
        user_id=owner,
        title="Study",
        description="Private text",
        status="todo",
        priority="normal",
        deadline_at=None,
        estimated_minutes=30,
        version=1,
        created_at=now,
        updated_at=now,
    )
    with Session(database_connection, join_transaction_mode="create_savepoint") as session:
        session.add_all(
            [
                UserModel(id=owner, email="task-owner@example.com"),
                UserModel(id=other, email="task-other@example.com"),
            ]
        )
        session.flush()
        repository: TaskRepository = SqlAlchemyTaskRepository(session)
        repository.create(task)
        session.commit()
        assert repository.get(owner, identifier) == task
        assert repository.get(other, identifier) is None
        assert repository.list(other, None, None, 100, 0) == []
        assert repository.list(owner, "done", None, 100, 0) == []
        assert repository.list(owner, None, "urgent", 100, 0) == []
        summary = repository.list(owner, "todo", "normal", 1, 0)[0]
        assert summary.id == identifier and not hasattr(summary, "description")
        assert repository.list(owner, None, None, 1, 1) == []
        changed = replace(task, title="Changed", version=2)
        repository.save(changed, 1)
        assert repository.get(owner, identifier) == changed
        for value in (task, replace(changed, user_id=other), replace(changed, id=uuid4())):
            with pytest.raises(TaskVersionConflict):
                repository.save(value, 1)
        session.execute(delete(UserModel).where(UserModel.id == owner))
        assert repository.get(owner, identifier) is None


@pytest.mark.parametrize(
    "values",
    [
        {"title": ""},
        {"title": "\t\n"},
        {"title": " bad "},
        {"description": "x" * 10001},
        {"status": "other"},
        {"priority": "other"},
        {"estimated_minutes": 0},
        {"estimated_minutes": 525601},
        {"version": 0},
        {"user_id": uuid4()},
    ],
)
def test_database_rejects_invalid_task_data(database_connection: Connection, values: dict) -> None:
    owner = uuid4()
    database_connection.execute(
        insert(UserModel).values(id=owner, email="task-constraints@example.com")
    )
    with pytest.raises(IntegrityError), database_connection.begin_nested():
        database_connection.execute(
            insert(TaskModel).values(**{"id": uuid4(), "user_id": owner, "title": "Valid"} | values)
        )


def test_independent_sessions_refresh_and_rollback(concurrent_engine: Engine) -> None:
    owner, identifier = uuid4(), uuid4()
    with Session(concurrent_engine) as session, session.begin():
        session.add(UserModel(id=owner, email="task-transactions@example.com"))
        session.flush()
        session.execute(insert(TaskModel).values(id=identifier, user_id=owner, title="Original"))
    with Session(concurrent_engine, expire_on_commit=False) as reader:
        repository = SqlAlchemyTaskRepository(reader)
        cached = reader.get(TaskModel, identifier)
        original = repository.get(owner, identifier)
        assert original and cached
        reader.commit()
        with Session(concurrent_engine) as writer, writer.begin():
            SqlAlchemyTaskRepository(writer).save(
                replace(original, title="Committed", version=2), 1
            )
        assert cached.title == "Original"
        stored = repository.get(owner, identifier)
        assert stored is not None and stored.title == "Committed"
        reader.rollback()
        with pytest.raises(RuntimeError), reader.begin():
            current = repository.get(owner, identifier)
            assert current
            repository.save(replace(current, title="Rolled back", version=3), 2)
            raise RuntimeError("Abort caller transaction")
        stored = repository.get(owner, identifier)
        assert stored is not None and stored.title == "Committed"
        reader.rollback()
        with Session(concurrent_engine) as writer, writer.begin():
            writer.execute(
                update(TaskModel).where(TaskModel.id == identifier).values(priority="high")
            )
        assert repository.list(owner, None, "high", 100, 0)[0].priority == "high"
