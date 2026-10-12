from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
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

from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication
from app.modules.workspace.application.service import WorkspaceService
from app.modules.workspace.domain.organization import WorkspaceConflict
from app.modules.workspace.infrastructure.orm import OrganizationModel
from app.modules.workspace.infrastructure.repository import SqlAlchemyOrganizations

BASE = "/api/v1/workspace"


def create_organization(client: TestClient, kind: str = "collections", **values) -> dict:
    response = client.post(
        f"{BASE}/{kind}", headers=csrf_headers(client), json={"name": "Training"} | values
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("kind", ["collections", "tags"])
def test_organization_crud_and_private_logs(calendar_client: TestClient, kind: str) -> None:
    with capture_json() as output:
        organization = create_organization(
            calendar_client, kind, name=" Private name ", color="#Aa00FF"
        )
        path = f"{BASE}/{kind}/{organization['id']}"
        assert organization["name"] == "Private name" and organization["color"] == "#aa00ff"
        assert "user_id" not in organization and organization["kind"] == kind.removesuffix("s")
        assert calendar_client.get(path).json() == organization
        listing = calendar_client.get(f"{BASE}/{kind}?limit=1&offset=0")
        assert listing.json()["items"] == [organization]
        assert listing.headers["cache-control"] == "no-store"
        changed = calendar_client.patch(
            path, headers=csrf_headers(calendar_client), json={"expected_version": 1, "color": None}
        )
        assert changed.status_code == 200 and changed.json()["name"] == "Private name"
        assert changed.json()["color"] is None and changed.json()["version"] == 2
        assert (
            calendar_client.patch(
                path,
                headers=csrf_headers(calendar_client),
                json={"expected_version": 1, "name": "Overwrite"},
            ).status_code
            == 409
        )
        assert (
            calendar_client.delete(
                path + "?expected_version=1", headers=csrf_headers(calendar_client)
            ).status_code
            == 409
        )
        assert (
            calendar_client.delete(
                path + "?expected_version=2", headers=csrf_headers(calendar_client)
            ).status_code
            == 204
        )
        assert calendar_client.get(path).status_code == 404
    assert "Private name" not in output.getvalue() and organization["id"] not in output.getvalue()
    assert any(row["event"] == "workspace.organization_deleted" for row in entries(output))


@pytest.mark.parametrize(
    "values",
    [
        {"name": " "},
        {"name": None},
        {"name": "x" * 101},
        {"name": "x\x00"},
        {"name": 12},
        {"color": "red"},
        {"color": "#abc"},
        {"kind": "tag"},
    ],
)
def test_invalid_metadata_is_rejected(calendar_client: TestClient, values: dict) -> None:
    assert (
        calendar_client.post(
            f"{BASE}/collections",
            headers=csrf_headers(calendar_client),
            json={"name": "T"} | values,
        ).status_code
        == 422
    )
    assert calendar_client.get(f"{BASE}/collections").json()["items"] == []


def test_kind_owner_csrf_session_and_query_bounds(
    calendar_client: TestClient,
    concurrent_engine: Engine,
    password_hash: str,
) -> None:
    organization = create_organization(calendar_client)
    path = f"{BASE}/collections/{organization['id']}"
    assert calendar_client.get(f"{BASE}/tags/{organization['id']}").status_code == 404
    for method, url, values in (
        ("POST", f"{BASE}/tags", {"name": "T"}),
        ("PATCH", path, {"expected_version": 1, "name": "T"}),
        ("DELETE", path + "?expected_version=1", None),
    ):
        assert calendar_client.request(method, url, json=values).status_code == 403
    for values in (
        {"expected_version": 1},
        {"expected_version": True, "name": "T"},
        {"expected_version": 1, "name": None},
    ):
        assert (
            calendar_client.patch(
                path, headers=csrf_headers(calendar_client), json=values
            ).status_code
            == 422
        )
    for query in ("limit=0", "limit=201", "offset=-1", "offset=2147483648"):
        assert calendar_client.get(f"{BASE}/collections?{query}").status_code == 422
    seed_user(concurrent_engine, "other@example.com", password_hash)
    browser_login(calendar_client, "other@example.com")
    assert calendar_client.get(path).status_code == 404
    assert calendar_client.get(f"{BASE}/collections").json()["items"] == []
    assert (
        calendar_client.patch(
            path, headers=csrf_headers(calendar_client), json={"expected_version": 1, "name": "T"}
        ).status_code
        == 404
    )
    assert (
        calendar_client.delete(
            path + "?expected_version=1", headers=csrf_headers(calendar_client)
        ).status_code
        == 404
    )
    calendar_client.cookies.clear()
    assert calendar_client.get(path).status_code == 401


def test_metadata_storage_failure_rolls_back(calendar_client: TestClient) -> None:
    organization = create_organization(calendar_client)
    path = f"{BASE}/collections/{organization['id']}"
    original = SqlAlchemyOrganizations.save

    def fail(self, value, expected_version):
        original(self, value, expected_version)
        raise SQLAlchemyError("private-workspace-sql")

    with patch.object(SqlAlchemyOrganizations, "save", fail), capture_json() as output:
        response = calendar_client.patch(
            path,
            headers=csrf_headers(calendar_client),
            json={"expected_version": 1, "name": "Private edit"},
        )
    assert response.status_code == 503 and "private" not in response.text
    assert "private-workspace-sql" not in output.getvalue()
    assert not any(row["event"] == "workspace.organization_updated" for row in entries(output))
    assert calendar_client.get(path).json() == organization


def test_concurrent_metadata_edits_reject_stale_version(
    calendar_client: TestClient, concurrent_engine: Engine
) -> None:
    organization = create_organization(calendar_client)
    identifier = UUID(organization["id"])
    with Session(concurrent_engine) as database:
        row = database.get(OrganizationModel, identifier)
        assert row
        owner = row.user_id

    def edit(name: str) -> bool:
        try:
            with Session(concurrent_engine) as database, database.begin():
                service = WorkspaceService(
                    SqlAlchemyOrganizations(database), SqlAlchemyUserAuthentication(database)
                )
                service.update(owner, "collection", identifier, {"name": name}, 1)
            return True
        except WorkspaceConflict:
            return False

    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(edit, name) for name in ("Chest", "Back")]
        assert sorted(future.result() for future in futures) == [False, True]
    stored = calendar_client.get(f"{BASE}/collections/{identifier}").json()
    assert stored["version"] == 2 and stored["name"] in ("Chest", "Back")
