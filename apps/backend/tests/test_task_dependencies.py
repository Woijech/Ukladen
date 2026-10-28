from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import create_autospec, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, delete, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_auth_http import csrf_headers
from test_auth_persistence import database_connection as database_connection
from test_auth_persistence import migration_config
from test_calendar_http import browser_settings as browser_settings
from test_calendar_http import calendar_client as calendar_client
from test_calendar_http import concurrent_engine as concurrent_engine
from test_calendar_http import live_client as live_client
from test_calendar_http import password_hash as password_hash
from test_calendar_http import settings as settings
from test_tasks_http import BASE, create_task
from test_tasks_service import NOW, setup_service

from alembic import command
from app.modules.tasks.application.dependencies import (
    TaskDependencies,
    TaskDependencyConflict,
    TaskDependencyService,
)
from app.modules.tasks.application.service import TaskService
from app.modules.tasks.domain.tasks import TaskNotFound, TaskTrashConflict, TaskVersionConflict
from app.modules.tasks.infrastructure.dependencies import SqlAlchemyTaskDependencies
from app.modules.tasks.infrastructure.orm import TaskDependencyModel, TaskModel
from app.modules.tasks.infrastructure.repository import SqlAlchemyTaskRepository
from app.modules.users.infrastructure.orm import UserModel
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication


def test_dependency_guards_and_noop_versions() -> None:
    tasks, repository, users = setup_service()
    owner = uuid4()
    task = tasks.create(owner, {"title": "Task"})
    predecessor = tasks.create(owner, {"title": "Predecessor"})
    state = {task.id: task, predecessor.id: predecessor}
    repository.get.side_effect = lambda _, identifier: state.get(identifier)
    links = create_autospec(TaskDependencies, instance=True)
    service = TaskDependencyService(tasks, links)
    links.reaches.return_value = False
    links.contains.return_value = False
    result = service.change(owner, task.id, predecessor.id, 1)
    assert result.version == 2
    users.lock_active.assert_called_with(owner)
    links.put.assert_called_once_with(owner, task.id, predecessor.id)
    links.contains.return_value = True
    assert service.change(owner, task.id, predecessor.id, 1) == task
    links.reaches.return_value = True
    with pytest.raises(TaskDependencyConflict):
        service.change(owner, task.id, predecessor.id, 1)
    with pytest.raises(TaskDependencyConflict):
        service.change(owner, task.id, task.id, 1)
    with pytest.raises(TaskVersionConflict):
        service.change(owner, task.id, predecessor.id, 2)
    with pytest.raises(TaskNotFound):
        service.change(owner, task.id, uuid4(), 1)
    state[predecessor.id] = replace(predecessor, trashed_at=NOW, trash_batch_id=predecessor.id)
    with pytest.raises(TaskTrashConflict):
        service.change(owner, task.id, predecessor.id, 1)
    links.delete.return_value = True
    assert service.change(owner, task.id, predecessor.id, 1, remove=True).version == 2


def test_dependency_http_versions_cycles_advisory_status_and_trash(
    calendar_client: TestClient,
) -> None:
    a, b, c = [create_task(calendar_client, title=title) for title in ("A", "B", "C")]
    headers = csrf_headers(calendar_client)
    path = f"{BASE}/{a['id']}/dependencies/{b['id']}"
    assert calendar_client.put(path, json={"expected_version": 1}).status_code == 403
    added = calendar_client.put(path, headers=headers, json={"expected_version": 1})
    assert added.status_code == 200, added.text
    assert added.json()["version"] == 2
    assert (
        calendar_client.put(path, headers=headers, json={"expected_version": 1}).status_code == 409
    )
    assert (
        calendar_client.put(path, headers=headers, json={"expected_version": 2}).json()["version"]
        == 2
    )
    second = calendar_client.put(
        f"{BASE}/{b['id']}/dependencies/{c['id']}", headers=headers, json={"expected_version": 1}
    )
    assert second.status_code == 200, second.text
    cycle = calendar_client.put(
        f"{BASE}/{c['id']}/dependencies/{a['id']}", headers=headers, json={"expected_version": 1}
    )
    assert cycle.status_code == 409 and cycle.json()["code"] == "task_dependency_conflict"
    listed = calendar_client.get(f"{BASE}/{a['id']}/dependencies").json()
    assert [item["id"] for item in listed["items"]] == [b["id"]]
    assert listed["has_unresolved_dependencies"]
    assert "description" not in listed["items"][0]
    # Manual completion remains possible while a predecessor is unfinished.
    done = calendar_client.patch(
        f"{BASE}/{a['id']}", headers=headers, json={"expected_version": 2, "status": "done"}
    )
    assert done.status_code == 200, done.text
    closed = calendar_client.patch(
        f"{BASE}/{b['id']}", headers=headers, json={"expected_version": 2, "status": "done"}
    )
    assert closed.status_code == 200, closed.text
    assert not calendar_client.get(f"{BASE}/{a['id']}/dependencies").json()[
        "has_unresolved_dependencies"
    ]
    assert (
        calendar_client.post(
            f"{BASE}/{b['id']}/trash", headers=headers, json={"expected_version": 3}
        ).status_code
        == 200
    )
    listed = calendar_client.get(f"{BASE}/{a['id']}/dependencies?offset=100").json()
    assert listed["items"] == [] and listed["has_unresolved_dependencies"]
    removed = calendar_client.request("DELETE", path, headers=headers, json={"expected_version": 3})
    assert removed.status_code == 200 and removed.json()["version"] == 4
    assert calendar_client.get(f"{BASE}/{b['id']}").json()["title"] == "B"
    assert calendar_client.get(f"{BASE}/{a['id']}/dependencies").json()["items"] == []


def test_dependencies_hide_foreign_ids_and_rollback(
    calendar_client: TestClient,
    concurrent_engine: Engine,
) -> None:
    a, b = create_task(calendar_client), create_task(calendar_client)
    with Session(concurrent_engine) as database, database.begin():
        owner = UserModel(email="dependency-foreign@example.com")
        database.add(owner)
        database.flush()
        foreign = TaskModel(id=uuid4(), user_id=owner.id, title="Private")
        database.add(foreign)
        identifier = foreign.id
    headers = csrf_headers(calendar_client)
    for other in (identifier, uuid4()):
        for task_id, predecessor_id in ((a["id"], other), (other, a["id"])):
            result = calendar_client.put(
                f"{BASE}/{task_id}/dependencies/{predecessor_id}",
                headers=headers,
                json={"expected_version": 1},
            )
            assert result.status_code == 404 and result.json()["code"] == "task_not_found"
        assert calendar_client.get(f"{BASE}/{other}/dependencies").status_code == 404
    with patch.object(SqlAlchemyTaskRepository, "save", side_effect=TaskVersionConflict):
        failed = calendar_client.put(
            f"{BASE}/{a['id']}/dependencies/{b['id']}",
            headers=headers,
            json={"expected_version": 1},
        )
    assert failed.status_code == 409
    assert calendar_client.get(f"{BASE}/{a['id']}/dependencies").json()["items"] == []


def test_concurrent_opposite_dependencies_cannot_create_cycle(
    calendar_client: TestClient,
    concurrent_engine: Engine,
) -> None:
    a, b = create_task(calendar_client), create_task(calendar_client)
    with Session(concurrent_engine) as database:
        owner = database.scalar(select(TaskModel.user_id).where(TaskModel.id == UUID(a["id"])))
        assert owner is not None

    def add(task: dict, predecessor: dict) -> str:
        with Session(concurrent_engine) as database:
            try:
                with database.begin():
                    tasks = TaskService(
                        SqlAlchemyTaskRepository(database), SqlAlchemyUserAuthentication(database)
                    )
                    TaskDependencyService(tasks, SqlAlchemyTaskDependencies(database)).change(
                        owner, UUID(task["id"]), UUID(predecessor["id"]), 1
                    )
                return "added"
            except TaskDependencyConflict:
                return "cycle"

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda pair: add(*pair), ((a, b), (b, a))))
    assert sorted(results) == ["added", "cycle"]


def test_dependency_migration_constraints_preservation_and_cascade(
    database_connection: Connection,
) -> None:
    config = migration_config(database_connection)
    command.downgrade(config, "0032_merge_ai_tasks")
    owner, other, a, b, c = [uuid4() for _ in range(5)]
    database_connection.execute(
        insert(UserModel),
        [
            {"id": owner, "email": "dependency-owner@example.com"},
            {"id": other, "email": "dependency-other@example.com"},
        ],
    )
    database_connection.execute(
        insert(TaskModel),
        [
            {"id": a, "user_id": owner, "title": "A"},
            {"id": b, "user_id": owner, "title": "B"},
            {"id": c, "user_id": other, "title": "Private"},
        ],
    )
    command.upgrade(config, "head")
    command.check(config)
    assert database_connection.scalar(select(TaskModel.title).where(TaskModel.id == a)) == "A"
    for values in (
        {"task_id": a, "predecessor_id": a, "user_id": owner},
        {"task_id": a, "predecessor_id": c, "user_id": owner},
        {"task_id": a, "predecessor_id": b, "user_id": other},
    ):
        with pytest.raises(IntegrityError), database_connection.begin_nested():
            database_connection.execute(insert(TaskDependencyModel).values(**values))
    database_connection.execute(
        insert(TaskDependencyModel).values(task_id=a, predecessor_id=b, user_id=owner)
    )
    with pytest.raises(RuntimeError, match="populated task dependencies"):
        command.downgrade(config, "0032_merge_ai_tasks")
    database_connection.execute(delete(UserModel).where(UserModel.id == owner))
    assert database_connection.scalar(select(TaskDependencyModel.task_id)) is None
    command.downgrade(config, "0032_merge_ai_tasks")
    command.upgrade(config, "head")
    command.check(config)
