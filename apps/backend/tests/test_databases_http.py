from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import patch
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_auth_http import browser_login, csrf_headers, seed_user
from test_logging import capture_json, entries
from test_notes_http import create_page
from test_workspace_http import browser_settings as browser_settings
from test_workspace_http import calendar_client as calendar_client
from test_workspace_http import concurrent_engine as concurrent_engine
from test_workspace_http import live_client as live_client
from test_workspace_http import password_hash as password_hash
from test_workspace_http import settings as settings

from app.modules.workspace.domain.organization import WorkspaceConflict
from app.modules.workspace.infrastructure.databases import SqlAlchemyDatabases, database_entity
from app.modules.workspace.infrastructure.orm import DatabaseModel

BASE = "/api/v1/workspace/databases"


def create_database(client: TestClient, **values) -> dict:
    response = client.post(BASE, headers=csrf_headers(client), json={"name": "Workouts"} | values)
    assert response.status_code == 201, response.text
    return response.json()


def test_database_metadata_versions_trash_and_restore(calendar_client: TestClient) -> None:
    page = create_page(calendar_client)
    with capture_json() as output:
        value = create_database(calendar_client, name=" Private database ", color="#Aa00FF")
        path = f"{BASE}/{value['id']}"
        assert value["name"] == "Private database" and value["color"] == "#aa00ff"
        assert value["version"] == value["schema_version"] == 1 and "user_id" not in value
        assert calendar_client.get(path).json() == value
        listing = calendar_client.get(BASE)
        assert listing.json()["items"] == [value] and listing.headers["cache-control"] == "no-store"
        changed = calendar_client.patch(
            path,
            headers=csrf_headers(calendar_client),
            json={"expected_version": 1, "name": "Renamed", "color": None},
        )
        assert changed.status_code == 200 and changed.json()["version"] == 2
        assert changed.json()["color"] is None and changed.json()["schema_version"] == 1
        assert (
            calendar_client.patch(
                path,
                headers=csrf_headers(calendar_client),
                json={"expected_version": 1, "name": "Stale"},
            ).status_code
            == 409
        )
        assert (
            calendar_client.post(
                path + "/restore",
                headers=csrf_headers(calendar_client),
                json={"expected_version": 2},
            ).status_code
            == 409
        )
        trashed = calendar_client.post(
            path + "/trash", headers=csrf_headers(calendar_client), json={"expected_version": 2}
        )
        assert trashed.status_code == 200 and trashed.json()["trashed_at"] is not None
        assert calendar_client.get(BASE).json()["items"] == []
        assert calendar_client.get(BASE + "?trashed=true").json()["items"] == [trashed.json()]
        assert (
            calendar_client.patch(
                path,
                headers=csrf_headers(calendar_client),
                json={"expected_version": 3, "name": "Trashed edit"},
            ).status_code
            == 409
        )
        restored = calendar_client.post(
            path + "/restore", headers=csrf_headers(calendar_client), json={"expected_version": 3}
        )
        assert (
            restored.status_code == 200
            and restored.json()["version"] == 4
            and restored.json()["trashed_at"] is None
        )
    assert value["id"] not in output.getvalue() and "Private database" not in output.getvalue()
    assert any(row["event"] == "workspace.database_restored" for row in entries(output))
    assert calendar_client.get(f"/api/v1/notes/pages/{page['id']}").json() == page


def test_database_auth_csrf_ownership_validation_and_pagination(
    calendar_client: TestClient, concurrent_engine: Engine, password_hash: str
) -> None:
    value = create_database(calendar_client)
    path = f"{BASE}/{value['id']}"
    for method, route, payload in (
        ("POST", BASE, {"name": "Missing CSRF"}),
        ("PATCH", path, {"expected_version": 1, "name": "Changed"}),
        ("POST", path + "/trash", {"expected_version": 1}),
        ("POST", path + "/restore", {"expected_version": 1}),
    ):
        assert calendar_client.request(method, route, json=payload).status_code == 403
    for changes in ({"name": " "}, {"color": "red"}, {"user_id": value["id"]}):
        assert (
            calendar_client.post(
                BASE, headers=csrf_headers(calendar_client), json={"name": "Invalid"} | changes
            ).status_code
            == 422
        )
    assert (
        calendar_client.patch(
            path, headers=csrf_headers(calendar_client), json={"expected_version": 1}
        ).status_code
        == 422
    )
    assert calendar_client.get(BASE + "?limit=1&offset=1").json()["items"] == []
    for query in ("limit=0", "limit=201", "offset=-1", "offset=2147483648"):
        assert calendar_client.get(BASE + "?" + query).status_code == 422
    seed_user(concurrent_engine, "other@example.com", password_hash)
    browser_login(calendar_client, "other@example.com")
    assert calendar_client.get(BASE).json()["items"] == []
    for method, suffix, payload in (
        ("GET", "", None),
        ("PATCH", "", {"expected_version": 1, "name": "Foreign"}),
        ("POST", "/trash", {"expected_version": 1}),
        ("POST", "/restore", {"expected_version": 1}),
    ):
        assert (
            calendar_client.request(
                method, path + suffix, headers=csrf_headers(calendar_client), json=payload
            ).status_code
            == 404
        )
    calendar_client.cookies.clear()
    assert calendar_client.get(BASE).status_code == 401
    assert calendar_client.get(path).status_code == 401


def test_database_rollback_and_compare_and_swap(
    calendar_client: TestClient, concurrent_engine: Engine
) -> None:
    value = create_database(calendar_client)
    path = f"{BASE}/{value['id']}"
    original = SqlAlchemyDatabases.save

    def fail(self, database, expected_version):
        original(self, database, expected_version)
        raise SQLAlchemyError("private-database-values")

    with patch.object(SqlAlchemyDatabases, "save", fail), capture_json() as output:
        result = calendar_client.patch(
            path,
            headers=csrf_headers(calendar_client),
            json={"expected_version": 1, "name": "Private update"},
        )
    assert (
        result.status_code == 503
        and "private" not in result.text
        and "private-database-values" not in output.getvalue()
    )
    assert not any(row["event"] == "workspace.database_updated" for row in entries(output))
    assert calendar_client.get(path).json() == value

    def edit(name: str) -> bool:
        try:
            with Session(concurrent_engine) as session, session.begin():
                row = session.get(DatabaseModel, UUID(value["id"]))
                assert row
                updated = replace(database_entity(row), name=name, version=2)
                SqlAlchemyDatabases(session).save(updated, 1)
            return True
        except WorkspaceConflict:
            return False

    with ThreadPoolExecutor(2) as workers:
        assert sorted(workers.map(edit, ["First", "Second"])) == [False, True]
    assert calendar_client.get(path).json()["version"] == 2
