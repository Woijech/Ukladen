from concurrent.futures import ThreadPoolExecutor
from typing import cast
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_auth_http import browser_login, csrf_headers, seed_user
from test_calendar_http import browser_settings as browser_settings
from test_calendar_http import calendar_client as calendar_client
from test_calendar_http import concurrent_engine as concurrent_engine
from test_calendar_http import live_client as live_client
from test_calendar_http import password_hash as password_hash
from test_calendar_http import settings as settings
from test_logging import capture_json, entries

from app.modules.notes.application.service import NoteService
from app.modules.notes.domain.pages import PageConflict
from app.modules.notes.infrastructure.orm import PageModel
from app.modules.notes.infrastructure.repository import SqlAlchemyPageRepository
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication

BASE = "/api/v1/notes/pages"


def create_page(client: TestClient, **values) -> dict:
    response = client.post(BASE, headers=csrf_headers(client), json={"title": "Training"} | values)
    assert response.status_code == 201, response.text
    return response.json()


def change(client: TestClient, page: dict, **values):
    return client.patch(
        f"{BASE}/{page['id']}",
        headers=csrf_headers(client),
        json={"expected_version": page["version"]} | values,
    )


def lifecycle(client: TestClient, page: dict, operation: str):
    return client.post(
        f"{BASE}/{page['id']}/{operation}",
        headers=csrf_headers(client),
        json={"expected_version": page["version"]},
    )


def test_independent_pages_hierarchy_versions_and_private_logs(calendar_client: TestClient) -> None:
    with capture_json() as output:
        root = create_page(calendar_client, title=" Training ", content="# private-body")
        child = create_page(calendar_client, title="Chest", parent_id=root["id"])
        path = f"{BASE}/{root['id']}"
        assert root["title"] == "Training" and root["content_format"] == "markdown"
        assert "user_id" not in root and root["version"] == 1
        assert calendar_client.get(path).json() == root
        listing = calendar_client.get(BASE).json()
        assert len(listing["items"]) == 2 and "content" not in listing["items"][0]
        assert calendar_client.get(f"{BASE}?roots_only=true").json()["items"][0]["id"] == root["id"]
        assert (
            calendar_client.get(f"{BASE}?parent_id={root['id']}").json()["items"][0]["id"]
            == child["id"]
        )
        updated = change(calendar_client, child, content="private-change", title="Chest day")
        assert updated.status_code == 200 and updated.json()["version"] == 2
        assert updated.json()["parent_id"] == root["id"]
        assert change(calendar_client, child, title="Overwrite").status_code == 409
        assert change(calendar_client, root, parent_id=child["id"]).status_code == 409
        assert change(calendar_client, root, parent_id=root["id"]).status_code == 409
        moved = change(calendar_client, updated.json(), parent_id=None)
        assert moved.status_code == 200 and moved.json()["parent_id"] is None
        assert calendar_client.get(f"{BASE}?parent_id={root['id']}").json()["items"] == []
    assert root["id"] not in output.getvalue()
    assert "private-body" not in output.getvalue() and "private-change" not in output.getvalue()
    assert any(row["event"] == "notes.page_created" for row in entries(output))
    assert calendar_client.get(BASE).headers["cache-control"] == "no-store"


def test_branch_trash_preserves_independently_trashed_children(calendar_client: TestClient) -> None:
    root = create_page(calendar_client)
    child = create_page(calendar_client, parent_id=root["id"])
    grandchild = create_page(calendar_client, parent_id=child["id"])
    separate = create_page(calendar_client, parent_id=root["id"])
    separate = lifecycle(calendar_client, separate, "trash").json()
    trashed = lifecycle(calendar_client, root, "trash")
    assert trashed.status_code == 200
    assert calendar_client.get(BASE).json()["items"] == []
    assert len(calendar_client.get(f"{BASE}?trashed=true").json()["items"]) == 4
    for page in (child, grandchild):
        stored = calendar_client.get(f"{BASE}/{page['id']}").json()
        assert stored["trash_batch_id"] == root["id"] and stored["version"] == 2
        assert lifecycle(calendar_client, stored, "restore").status_code == 409
        assert change(calendar_client, stored, title="Edit deleted").status_code == 409
    assert lifecycle(calendar_client, separate, "restore").status_code == 409
    assert create_page_error(calendar_client, {"title": "Child", "parent_id": root["id"]}) == 409
    assert lifecycle(calendar_client, root, "restore").status_code == 409
    restored = lifecycle(calendar_client, trashed.json(), "restore")
    assert restored.status_code == 200 and restored.json()["version"] == 3
    assert len(calendar_client.get(BASE).json()["items"]) == 3
    assert calendar_client.get(f"{BASE}/{separate['id']}").json() == separate
    assert lifecycle(calendar_client, separate, "restore").status_code == 200
    assert len(calendar_client.get(BASE).json()["items"]) == 4


def create_page_error(client: TestClient, payload: dict) -> int:
    return client.post(BASE, headers=csrf_headers(client), json=payload).status_code


@pytest.mark.parametrize(
    "payload",
    [
        {"title": " "},
        {"title": "x" * 201},
        {"title": 123},
        {"title": "T", "content": None},
        {"title": "T", "content": "x" * 100001},
        {"title": "T", "content": "null\x00byte"},
        {"title": "T", "user_id": str(uuid4())},
        {"title": "T", "parent_id": "invalid"},
    ],
)
def test_page_input_validation(calendar_client: TestClient, payload: dict) -> None:
    assert create_page_error(calendar_client, payload) == 422
    assert calendar_client.get(BASE).json()["items"] == []


@pytest.mark.parametrize(
    "payload",
    [
        {"expected_version": 1},
        {"expected_version": True, "title": "T"},
        {"expected_version": 0, "title": "T"},
        {"expected_version": 1, "title": None},
        {"expected_version": 1, "content": None},
        {"expected_version": 1, "extra": "T"},
    ],
)
def test_patch_validation(calendar_client: TestClient, payload: dict) -> None:
    page = create_page(calendar_client)
    assert (
        calendar_client.patch(
            f"{BASE}/{page['id']}", headers=csrf_headers(calendar_client), json=payload
        ).status_code
        == 422
    )
    assert calendar_client.get(f"{BASE}/{page['id']}").json() == page


def test_access_controls(
    calendar_client: TestClient, concurrent_engine: Engine, password_hash: str
) -> None:
    page = create_page(calendar_client)
    path = f"{BASE}/{page['id']}"
    for method, url, payload in (
        ("POST", BASE, {"title": "T"}),
        ("PATCH", path, {"expected_version": 1, "title": "T"}),
        ("POST", path + "/trash", {"expected_version": 1}),
        ("POST", path + "/restore", {"expected_version": 1}),
    ):
        assert calendar_client.request(method, url, json=payload).status_code == 403
    seed_user(concurrent_engine, "other@example.com", password_hash)
    browser_login(calendar_client, "other@example.com")
    assert calendar_client.get(path).status_code == 404
    assert calendar_client.get(BASE).json()["items"] == []
    assert create_page_error(calendar_client, {"title": "T", "parent_id": page["id"]}) == 404
    assert change(calendar_client, page, title="T").status_code == 404
    assert lifecycle(calendar_client, page, "trash").status_code == 404
    assert lifecycle(calendar_client, page, "restore").status_code == 404
    own = create_page(calendar_client)
    assert change(calendar_client, own, parent_id=page["id"]).status_code == 404
    calendar_client.cookies.clear()
    assert calendar_client.get(BASE).status_code == 401
    assert calendar_client.get(path).status_code == 401


def test_write_failure_rolls_back(calendar_client: TestClient) -> None:
    application = cast(FastAPI, calendar_client.app)
    original = SqlAlchemyPageRepository.create

    def fail(self, page):
        original(self, page)
        raise SQLAlchemyError("private-page-sql")

    with patch.object(SqlAlchemyPageRepository, "create", fail), capture_json() as output:
        response = calendar_client.post(
            BASE, headers=csrf_headers(calendar_client), json={"title": "T"}
        )
    assert response.status_code == 503 and "private" not in response.text
    assert "private-page-sql" not in output.getvalue()
    assert not any(row["event"] == "notes.page_created" for row in entries(output))
    with application.state.session_factory() as database:
        assert database.scalar(select(PageModel)) is None


def test_concurrent_moves_cannot_create_cycle(
    calendar_client: TestClient, concurrent_engine: Engine
) -> None:
    first, second = create_page(calendar_client), create_page(calendar_client)
    with Session(concurrent_engine) as database:
        row = database.get(PageModel, UUID(first["id"]))
        assert row is not None
        owner = row.user_id

    def move(page: dict, parent: dict) -> bool:
        try:
            with Session(concurrent_engine) as database, database.begin():
                notes = NoteService(
                    SqlAlchemyPageRepository(database), SqlAlchemyUserAuthentication(database)
                )
                notes.update(owner, UUID(page["id"]), {"parent_id": UUID(parent["id"])}, 1)
            return True
        except PageConflict:
            return False

    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(move, first, second), pool.submit(move, second, first)]
        assert sorted(future.result() for future in futures) == [False, True]
