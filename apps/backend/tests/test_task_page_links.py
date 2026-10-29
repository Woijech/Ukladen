from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, insert, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from test_auth_http import browser_login, csrf_headers, seed_user
from test_auth_persistence import migration_config
from test_calendar_http import browser_settings as browser_settings
from test_calendar_http import calendar_client as calendar_client
from test_calendar_http import concurrent_engine as concurrent_engine
from test_calendar_http import live_client as live_client
from test_calendar_http import password_hash as password_hash
from test_calendar_http import settings as settings
from test_notes_http import BASE as NOTES
from test_notes_http import create_page, lifecycle
from test_tasks_http import BASE as TASKS
from test_tasks_http import create_task

from alembic import command
from app.modules.relations.infrastructure.orm import TaskPageLinkModel
from app.modules.relations.infrastructure.task_links import SqlAlchemyTaskPageLinks
from app.modules.tasks.infrastructure.orm import TaskModel
from app.modules.users.infrastructure.orm import UserModel

BASE = "/api/v1/relations"


def test_links_are_explicit_idempotent_independent_and_survive_trash(
    calendar_client: TestClient,
) -> None:
    task = create_task(calendar_client, description="Private task body")
    page = create_page(calendar_client, content="Private page body")
    path = f"{BASE}/tasks/{task['id']}/pages/{page['id']}"
    pages = f"{BASE}/tasks/{task['id']}/pages"
    tasks = f"{BASE}/pages/{page['id']}/tasks"
    headers = csrf_headers(calendar_client)
    for _ in range(2):
        linked = calendar_client.put(path, headers=headers)
        assert linked.status_code == 200, linked.text
        assert "content" not in linked.json() and "user_id" not in linked.json()
    listed = calendar_client.get(pages)
    assert listed.headers["cache-control"] == "no-store"
    assert [item["id"] for item in listed.json()["items"]] == [page["id"]]
    assert calendar_client.get(pages + "?offset=1").json()["items"] == []
    linked_task = calendar_client.get(tasks).json()["items"][0]
    assert linked_task["id"] == task["id"] and "description" not in linked_task
    assert calendar_client.get(f"{TASKS}/{task['id']}").json() == task
    trashed_page = lifecycle(calendar_client, page, "trash")
    assert trashed_page.status_code == 200
    assert calendar_client.get(pages).json()["items"][0]["trashed_at"] is not None
    assert calendar_client.put(path, headers=headers).status_code == 409
    trashed_task = calendar_client.post(
        f"{TASKS}/{task['id']}/trash", headers=headers, json={"expected_version": 1}
    )
    assert trashed_task.status_code == 200
    assert calendar_client.get(tasks).json()["items"][0]["trashed_at"] is not None
    assert calendar_client.delete(path, headers=headers).status_code == 204
    assert calendar_client.get(pages).json()["items"] == []
    assert calendar_client.get(tasks).json()["items"] == []
    assert calendar_client.get(f"{NOTES}/{page['id']}").json()["content"] == "Private page body"
    assert calendar_client.get(f"{TASKS}/{task['id']}").json()["description"] == "Private task body"


def test_link_owner_csrf_pagination_and_rollback(
    calendar_client: TestClient,
    concurrent_engine: Engine,
    password_hash: str,
) -> None:
    task, page = create_task(calendar_client), create_page(calendar_client)
    path = f"{BASE}/tasks/{task['id']}/pages/{page['id']}"
    assert calendar_client.put(path).status_code == 403
    assert calendar_client.delete(path).status_code == 403
    original = SqlAlchemyTaskPageLinks.put

    def fail(self, *args):
        original(self, *args)
        raise SQLAlchemyError("private-task-link-failure")

    with patch.object(SqlAlchemyTaskPageLinks, "put", fail):
        result = calendar_client.put(path, headers=csrf_headers(calendar_client))
    assert result.status_code == 503 and "private" not in result.text
    assert calendar_client.get(f"{BASE}/tasks/{task['id']}/pages").json()["items"] == []
    for suffix in ("?limit=201", "?offset=-1"):
        assert calendar_client.get(f"{BASE}/tasks/{task['id']}/pages{suffix}").status_code == 422
    seed_user(concurrent_engine, "foreign-task-link@example.com", password_hash)
    browser_login(calendar_client, "foreign-task-link@example.com")
    own_task, own_page = create_task(calendar_client), create_page(calendar_client)
    headers = csrf_headers(calendar_client)
    for route in (
        path,
        f"{BASE}/tasks/{own_task['id']}/pages/{page['id']}",
        f"{BASE}/tasks/{task['id']}/pages/{own_page['id']}",
    ):
        assert calendar_client.put(route, headers=headers).status_code == 404
        assert calendar_client.delete(route, headers=headers).status_code == 404
    assert calendar_client.get(f"{BASE}/tasks/{task['id']}/pages").status_code == 404
    assert calendar_client.get(f"{BASE}/pages/{page['id']}/tasks").status_code == 404
    calendar_client.cookies.clear()
    assert calendar_client.get(f"{BASE}/tasks/{own_task['id']}/pages").status_code == 401


def test_link_migration_owner_constraints_and_preserving_downgrade(
    calendar_client: TestClient,
    concurrent_engine: Engine,
) -> None:
    task, page = create_task(calendar_client), create_page(calendar_client)
    with concurrent_engine.begin() as connection:
        config = migration_config(connection)
        command.downgrade(config, "0033_task_dependencies")
        command.upgrade(config, "head")
        command.check(config)
    path = f"{BASE}/tasks/{task['id']}/pages/{page['id']}"
    assert calendar_client.put(path, headers=csrf_headers(calendar_client)).status_code == 200
    with Session(concurrent_engine) as database, database.begin():
        row = database.get(TaskModel, UUID(task["id"]))
        assert row is not None
        foreign = UserModel(email="invalid-task-link@example.com")
        database.add(foreign)
        database.flush()
        with pytest.raises(IntegrityError), database.begin_nested():
            database.execute(
                insert(TaskPageLinkModel).values(
                    task_id=UUID(task["id"]), page_id=UUID(page["id"]), user_id=foreign.id
                )
            )
        config = migration_config(database.connection())
        with pytest.raises(RuntimeError, match="populated task page links"):
            command.downgrade(config, "0033_task_dependencies")
        database.execute(delete(UserModel).where(UserModel.id == row.user_id))
        assert database.scalar(select(TaskPageLinkModel.task_id)) is None
        command.downgrade(config, "0033_task_dependencies")
        command.upgrade(config, "head")
        command.check(config)
