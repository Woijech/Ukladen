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
        {"parent_id": str(uuid4())},
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
    assert not any(path.startswith(f"{BASE}/") and path != f"{BASE}/{{task_id}}" for path in paths)
