import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_auth_http import csrf_headers
from test_calendar_http import browser_settings as browser_settings
from test_calendar_http import calendar_client as calendar_client
from test_calendar_http import concurrent_engine as concurrent_engine
from test_calendar_http import live_client as live_client
from test_calendar_http import password_hash as password_hash
from test_calendar_http import settings as settings
from test_logging import capture_json, entries

from app.modules.tasks.application.service import TaskService
from app.modules.tasks.infrastructure.orm import TaskModel
from app.modules.tasks.infrastructure.repository import SqlAlchemyTaskRepository
from app.modules.users.infrastructure.orm import UserModel
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication

BASE = "/api/v1/tasks"


def create_task(client: TestClient, **values) -> dict:
    response = client.post(BASE, headers=csrf_headers(client), json={"title": " Study "} | values)
    assert response.status_code == 201, response.text
    return response.json()


def test_independent_task_http_flow_filters_versions_and_private_logs(
    calendar_client: TestClient,
) -> None:
    with capture_json() as output:
        task = create_task(
            calendar_client,
            description="private-task-text",
            estimated_minutes=90,
            deadline_at="2020-10-21T18:00:00+03:00",
        )
        assert task["title"] == "Study" and task["version"] == 1
        assert task["parent_id"] is None
        assert task["deadline_at"] == "2020-10-21T15:00:00Z" and task["is_overdue"]
        assert "user_id" not in task and task["status"] == "todo" and task["priority"] == "normal"
        path = f"{BASE}/{task['id']}"
        assert calendar_client.get(path).json() == task
        listed = calendar_client.get(BASE)
        assert listed.headers["cache-control"] == "no-store"
        assert listed.json()["items"][0]["id"] == task["id"]
        assert "description" not in listed.json()["items"][0]
        assert calendar_client.get(f"{BASE}?status=done").json()["items"] == []
        assert calendar_client.get(f"{BASE}?priority=urgent").json()["items"] == []
        assert calendar_client.get(f"{BASE}?limit=1&offset=1").json()["items"] == []
        changed = calendar_client.patch(
            path,
            headers=csrf_headers(calendar_client),
            json={
                "expected_version": 1,
                "status": "done",
                "priority": "high",
                "description": None,
            },
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["version"] == 2 and not changed.json()["is_overdue"]
        assert changed.json()["description"] is None and changed.json()["estimated_minutes"] == 90
        stale = calendar_client.patch(
            path,
            headers=csrf_headers(calendar_client),
            json={"expected_version": 1, "title": "Overwrite"},
        )
        assert stale.status_code == 409 and stale.json()["code"] == "task_version_conflict"
        reopened = calendar_client.patch(
            path,
            headers=csrf_headers(calendar_client),
            json={
                "expected_version": 2,
                "status": "todo",
                "deadline_at": None,
                "estimated_minutes": None,
            },
        )
        assert reopened.status_code == 200 and reopened.json()["deadline_at"] is None
        calendar = calendar_client.get(
            "/api/v1/calendar/events?date_from=2026-10-21&date_to=2026-10-21"
        )
        assert calendar.status_code == 200 and calendar.json()["events"] == []
        assert (
            calendar_client.get(f"{BASE}?status=todo&priority=high").json()["items"][0]["version"]
            == 3
        )
    assert "private-task-text" not in output.getvalue()
    assert any(row["event"] == "tasks.task_created" for row in entries(output))
    assert any(row["event"] == "tasks.task_updated" for row in entries(output))


@pytest.mark.parametrize(
    "values",
    [
        {"title": "\t\n"},
        {"title": None},
        {"title": "bad\x00text"},
        {"description": "\ud800"},
        {"status": None},
        {"status": "invalid"},
        {"priority": "invalid"},
        {"deadline_at": "2026-10-21"},
        {"deadline_at": "2026-10-21T18:00:00"},
        {"deadline_at": 1792600000},
        {"estimated_minutes": True},
        {"estimated_minutes": "30"},
        {"estimated_minutes": 0},
        {"estimated_minutes": 525601},
        {"user_id": str(uuid4())},
        {"parent_id": "not-a-uuid"},
    ],
)
def test_invalid_task_creation(calendar_client: TestClient, values: dict) -> None:
    response = calendar_client.post(
        BASE,
        headers=csrf_headers(calendar_client) | {"Content-Type": "application/json"},
        content=json.dumps({"title": "Valid"} | values),
    )
    assert response.status_code == 422, response.text
    assert calendar_client.get(BASE).json()["items"] == []


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"expected_version": 1},
        {"expected_version": True, "title": "Bad"},
        {"expected_version": "1", "title": "Bad"},
        {"expected_version": 1, "status": None},
        {"expected_version": 1, "priority": None},
        {"expected_version": 1, "title": None},
        {"expected_version": 1, "created_at": "2026-10-21T00:00:00Z"},
    ],
)
def test_invalid_patch_preserves_task(calendar_client: TestClient, values: dict) -> None:
    task = create_task(calendar_client)
    path = f"{BASE}/{task['id']}"
    assert (
        calendar_client.patch(path, headers=csrf_headers(calendar_client), json=values).status_code
        == 422
    )
    assert calendar_client.get(path).json() == task


def test_authentication_registration_and_csrf_guards(
    calendar_client: TestClient, concurrent_engine: Engine
) -> None:
    task = create_task(calendar_client)
    path = f"{BASE}/{task['id']}"
    assert calendar_client.post(BASE, json={"title": "Denied"}).status_code == 403
    headers = csrf_headers(calendar_client) | {"Origin": "https://foreign.example"}
    assert (
        calendar_client.patch(
            path, headers=headers, json={"expected_version": 1, "title": "Denied"}
        ).status_code
        == 403
    )
    with Session(concurrent_engine) as session, session.begin():
        session.execute(update(UserModel).values(email_verified_at=None))
    denied = calendar_client.get(BASE)
    assert denied.status_code == 403 and denied.json()["code"] == "registration_incomplete"
    with Session(concurrent_engine) as session, session.begin():
        session.execute(
            update(UserModel).values(email_verified_at=datetime.now(UTC), status="disabled")
        )
    assert calendar_client.get(path).status_code == 401
    calendar_client.cookies.clear()
    assert calendar_client.get(BASE).status_code == 401
    assert calendar_client.post(BASE, json={"title": "Denied"}).status_code == 401


def test_foreign_tasks_match_missing_tasks(
    calendar_client: TestClient, concurrent_engine: Engine
) -> None:
    with Session(concurrent_engine) as session, session.begin():
        other = UserModel(email="foreign-task@example.com")
        session.add(other)
        session.flush()
        task = TaskService(
            SqlAlchemyTaskRepository(session), SqlAlchemyUserAuthentication(session)
        ).create(other.id, {"title": "Foreign private task"})
    for identifier in (task.id, uuid4()):
        response = calendar_client.get(f"{BASE}/{identifier}")
        assert response.status_code == 404 and response.json()["code"] == "task_not_found"
        assert (
            calendar_client.patch(
                f"{BASE}/{identifier}",
                headers=csrf_headers(calendar_client),
                json={"expected_version": 1, "title": "Steal"},
            ).status_code
            == 404
        )
    assert calendar_client.get(BASE).json()["items"] == []


def test_subtask_http_tree_filters_and_completion_guards(calendar_client: TestClient) -> None:
    root = create_task(calendar_client, title="Root")
    child = create_task(calendar_client, title="Child", parent_id=root["id"])
    grandchild = create_task(calendar_client, title="Grandchild", parent_id=child["id"])
    assert child["parent_id"] == root["id"]
    assert grandchild["parent_id"] == child["id"]
    assert len(calendar_client.get(BASE).json()["items"]) == 3
    roots = calendar_client.get(f"{BASE}?roots_only=true").json()["items"]
    assert [item["id"] for item in roots] == [root["id"]]
    children = calendar_client.get(f"{BASE}?parent_id={root['id']}").json()["items"]
    assert [item["id"] for item in children] == [child["id"]]
    assert calendar_client.get(f"{BASE}?parent_id={grandchild['id']}").json()["items"] == []
    assert calendar_client.get(f"{BASE}?parent_id={root['id']}&roots_only=true").status_code == 422
    assert calendar_client.get(f"{BASE}?parent_id={uuid4()}").status_code == 404
    cycle = calendar_client.patch(
        f"{BASE}/{root['id']}",
        headers=csrf_headers(calendar_client),
        json={"expected_version": 1, "parent_id": grandchild["id"]},
    )
    assert cycle.status_code == 409 and cycle.json()["code"] == "task_hierarchy_conflict"
    blocked = calendar_client.patch(
        f"{BASE}/{root['id']}",
        headers=csrf_headers(calendar_client),
        json={"expected_version": 1, "status": "done"},
    )
    assert blocked.status_code == 409 and blocked.json()["code"] == "task_hierarchy_conflict"
    for task in (grandchild, child, root):
        response = calendar_client.patch(
            f"{BASE}/{task['id']}",
            headers=csrf_headers(calendar_client),
            json={"expected_version": 1, "status": "done"},
        )
        assert response.status_code == 200, response.text
    assert calendar_client.get(f"{BASE}/{root['id']}").json()["status"] == "done"
    assert calendar_client.get(f"{BASE}/{child['id']}").json()["status"] == "done"
    rejected = calendar_client.post(
        BASE,
        headers=csrf_headers(calendar_client),
        json={"title": "Open", "parent_id": root["id"]},
    )
    assert rejected.status_code == 409 and rejected.json()["code"] == "task_hierarchy_conflict"
    rejected = calendar_client.patch(
        f"{BASE}/{grandchild['id']}",
        headers=csrf_headers(calendar_client),
        json={"expected_version": 2, "status": "todo"},
    )
    assert rejected.status_code == 409 and rejected.json()["code"] == "task_hierarchy_conflict"
    detached = calendar_client.patch(
        f"{BASE}/{grandchild['id']}",
        headers=csrf_headers(calendar_client),
        json={"expected_version": 2, "parent_id": None, "status": "todo"},
    )
    assert detached.status_code == 200, detached.text
    assert detached.json()["parent_id"] is None and detached.json()["status"] == "todo"
    assert {
        item["id"] for item in calendar_client.get(f"{BASE}?roots_only=true").json()["items"]
    } == {
        root["id"],
        grandchild["id"],
    }


def test_task_trash_restores_only_its_batch_and_respects_completed_ancestors(
    calendar_client: TestClient,
) -> None:
    root = create_task(calendar_client, title="Root")
    child = create_task(calendar_client, title="Child", parent_id=root["id"])
    grandchild = create_task(calendar_client, title="Grandchild", parent_id=child["id"])
    sibling = create_task(calendar_client, title="Sibling", parent_id=root["id"])
    headers = csrf_headers(calendar_client)

    def trash(task: dict) -> dict:
        response = calendar_client.post(
            f"{BASE}/{task['id']}/trash",
            headers=headers,
            json={"expected_version": task["version"]},
        )
        assert response.status_code == 200, response.text
        return response.json()

    grandchild = trash(grandchild)
    root = trash(root)
    assert root["trash_batch_id"] == root["id"]
    assert root["trashed_at"] is not None
    assert calendar_client.get(BASE).json()["items"] == []
    trashed = calendar_client.get(f"{BASE}?trashed=true").json()["items"]
    assert {item["id"] for item in trashed} == {
        root["id"],
        child["id"],
        grandchild["id"],
        sibling["id"],
    }
    assert (
        next(item for item in trashed if item["id"] == grandchild["id"])["trash_batch_id"]
        == grandchild["id"]
    )
    blocked = calendar_client.post(
        f"{BASE}/{child['id']}/restore", headers=headers, json={"expected_version": 2}
    )
    assert blocked.status_code == 409 and blocked.json()["code"] == "task_trash_conflict"
    stale = calendar_client.post(
        f"{BASE}/{root['id']}/restore", headers=headers, json={"expected_version": 1}
    )
    assert stale.status_code == 409 and stale.json()["code"] == "task_version_conflict"
    root = calendar_client.post(
        f"{BASE}/{root['id']}/restore", headers=headers, json={"expected_version": 2}
    ).json()
    assert root["trashed_at"] is None and root["version"] == 3
    assert {item["id"] for item in calendar_client.get(BASE).json()["items"]} == {
        root["id"],
        child["id"],
        sibling["id"],
    }
    assert [item["id"] for item in calendar_client.get(f"{BASE}?trashed=true").json()["items"]] == [
        grandchild["id"]
    ]
    assert (
        calendar_client.patch(
            f"{BASE}/{grandchild['id']}",
            headers=headers,
            json={"expected_version": 2, "title": "Blocked"},
        ).json()["code"]
        == "task_trash_conflict"
    )
    assert (
        calendar_client.post(
            BASE, headers=headers, json={"title": "Blocked", "parent_id": grandchild["id"]}
        ).json()["code"]
        == "task_trash_conflict"
    )

    completion = calendar_client.patch(
        f"{BASE}/{root['id']}", headers=headers, json={"expected_version": 3, "status": "done"}
    )
    assert completion.status_code == 409
    for identifier in (child["id"], sibling["id"]):
        current = calendar_client.get(f"{BASE}/{identifier}").json()
        response = calendar_client.patch(
            f"{BASE}/{identifier}",
            headers=headers,
            json={"expected_version": current["version"], "status": "done"},
        )
        assert response.status_code == 200, response.text
    completion = calendar_client.patch(
        f"{BASE}/{root['id']}", headers=headers, json={"expected_version": 3, "status": "done"}
    )
    assert completion.status_code == 200, completion.text
    blocked = calendar_client.post(
        f"{BASE}/{grandchild['id']}/restore", headers=headers, json={"expected_version": 2}
    )
    assert blocked.status_code == 409 and blocked.json()["code"] == "task_hierarchy_conflict"
    assert calendar_client.get(f"{BASE}/{grandchild['id']}").json()["trashed_at"] is not None


def test_task_trash_requires_owner_csrf_and_exact_version(
    calendar_client: TestClient, concurrent_engine: Engine
) -> None:
    task = create_task(calendar_client)
    path = f"{BASE}/{task['id']}"
    assert calendar_client.post(f"{path}/trash", json={"expected_version": 1}).status_code == 403
    for payload in ({}, {"expected_version": True}, {"expected_version": 1, "extra": 1}):
        assert (
            calendar_client.post(
                f"{path}/trash", headers=csrf_headers(calendar_client), json=payload
            ).status_code
            == 422
        )
    with Session(concurrent_engine) as session, session.begin():
        other = UserModel(email="foreign-trash@example.com")
        session.add(other)
        session.flush()
        foreign = TaskService(
            SqlAlchemyTaskRepository(session), SqlAlchemyUserAuthentication(session)
        ).create(other.id, {"title": "Foreign"})
    for operation in ("trash", "restore"):
        for identifier in (foreign.id, uuid4()):
            result = calendar_client.post(
                f"{BASE}/{identifier}/{operation}",
                headers=csrf_headers(calendar_client),
                json={"expected_version": 1},
            )
            assert result.status_code == 404 and result.json()["code"] == "task_not_found"
    trashed = calendar_client.post(
        f"{path}/trash", headers=csrf_headers(calendar_client), json={"expected_version": 1}
    )
    assert trashed.status_code == 200
    repeated = calendar_client.post(
        f"{path}/trash", headers=csrf_headers(calendar_client), json={"expected_version": 2}
    )
    assert repeated.status_code == 409 and repeated.json()["code"] == "task_trash_conflict"
    restored = calendar_client.post(
        f"{path}/restore", headers=csrf_headers(calendar_client), json={"expected_version": 2}
    )
    assert restored.status_code == 200
    repeated = calendar_client.post(
        f"{path}/restore", headers=csrf_headers(calendar_client), json={"expected_version": 3}
    )
    assert repeated.status_code == 409 and repeated.json()["code"] == "task_trash_conflict"


def test_missing_and_foreign_parent_references_are_indistinguishable(
    calendar_client: TestClient, concurrent_engine: Engine
) -> None:
    with Session(concurrent_engine) as session, session.begin():
        other = UserModel(email="foreign-parent@example.com")
        session.add(other)
        session.flush()
        foreign = TaskService(
            SqlAlchemyTaskRepository(session), SqlAlchemyUserAuthentication(session)
        ).create(other.id, {"title": "Private parent"})
    own = create_task(calendar_client, title="Own")
    for parent_id in (str(foreign.id), str(uuid4())):
        created = calendar_client.post(
            BASE,
            headers=csrf_headers(calendar_client),
            json={"title": "Hidden parent", "parent_id": parent_id},
        )
        moved = calendar_client.patch(
            f"{BASE}/{own['id']}",
            headers=csrf_headers(calendar_client),
            json={"expected_version": 1, "parent_id": parent_id},
        )
        listed = calendar_client.get(f"{BASE}?parent_id={parent_id}")
        for response in (created, moved, listed):
            assert response.status_code == 404
            assert response.json()["code"] == "task_not_found"
    assert calendar_client.get(f"{BASE}/{own['id']}").json() == own


def test_concurrent_edits_have_one_winner(
    calendar_client: TestClient, concurrent_engine: Engine
) -> None:
    task = create_task(calendar_client)
    headers = csrf_headers(calendar_client)

    def edit(title):
        return calendar_client.patch(
            f"{BASE}/{task['id']}", headers=headers, json={"expected_version": 1, "title": title}
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(edit, ("First", "Second")))
    assert sorted(response.status_code for response in results) == [200, 409]
    with Session(concurrent_engine) as session:
        row = session.get(TaskModel, UUID(task["id"]))
        assert row and row.version == 2 and row.title in ("First", "Second")


def test_concurrent_parent_completion_and_child_creation_keep_tree_consistent(
    calendar_client: TestClient,
) -> None:
    root = create_task(calendar_client, title="Parent")
    headers = csrf_headers(calendar_client)

    def complete_parent():
        return calendar_client.patch(
            f"{BASE}/{root['id']}",
            headers=headers,
            json={"expected_version": 1, "status": "done"},
        )

    def create_child():
        return calendar_client.post(
            BASE,
            headers=headers,
            json={"title": "Child", "parent_id": root["id"]},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        finish = executor.submit(complete_parent)
        add_child = executor.submit(create_child)
        results = (finish.result(), add_child.result())
    assert sorted(response.status_code for response in results) in ([200, 409], [201, 409])
    parent = calendar_client.get(f"{BASE}/{root['id']}").json()
    children = calendar_client.get(f"{BASE}?parent_id={root['id']}").json()["items"]
    assert (parent["status"] == "done") == (children == [])


@pytest.mark.parametrize("failure", ["write", "commit"])
def test_database_failure_is_sanitized_and_rolls_back(
    calendar_client: TestClient,
    concurrent_engine: Engine,
    failure: str,
) -> None:
    task = create_task(calendar_client)
    path = f"{BASE}/{task['id']}"
    original = SqlAlchemyTaskRepository.save

    def fail_after_write(self, value, version):
        original(self, value, version)
        if failure == "write":
            raise SQLAlchemyError("private-connection-details")

        def fail_commit(session):
            raise SQLAlchemyError("private-connection-details")

        event.listen(self.session, "before_commit", fail_commit)

    with patch.object(SqlAlchemyTaskRepository, "save", fail_after_write):
        response = calendar_client.patch(
            path,
            headers=csrf_headers(calendar_client),
            json={"expected_version": 1, "title": "Must roll back"},
        )
    assert response.status_code == 503 and "private-connection-details" not in response.text
    assert calendar_client.get(path).json() == task
    with Session(concurrent_engine) as session:
        assert len(list(session.scalars(select(TaskModel)))) == 1


def test_openapi_exposes_only_delivered_operations(calendar_client: TestClient) -> None:
    paths = calendar_client.get("/api/openapi.json").json()["paths"]
    assert set(paths[BASE]) == {"get", "post"}
    assert set(paths[f"{BASE}/{{task_id}}"]) == {"get", "patch"}
    assert {path for path in paths if path.startswith(f"{BASE}/")} == {
        f"{BASE}/{{task_id}}",
        f"{BASE}/{{task_id}}/trash",
        f"{BASE}/{{task_id}}/restore",
        f"{BASE}/{{task_id}}/dependencies",
        f"{BASE}/{{task_id}}/dependencies/{{predecessor_id}}",
        f"{BASE}/planning/plans",
        f"{BASE}/planning/plans/{{plan_id}}",
        f"{BASE}/planning/plans/{{plan_id}}/apply",
        f"{BASE}/planning/preferences",
        f"{BASE}/planning/sessions",
        f"{BASE}/planning/sessions/check",
        f"{BASE}/planning/sessions/{{session_id}}",
    }
