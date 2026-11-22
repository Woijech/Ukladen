from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from test_auth_http import browser_login, csrf_headers, seed_user
from test_auth_sessions import migration_config
from test_database_views_http import create_view, view_path
from test_databases_http import create_database
from test_workspace_http import browser_settings as browser_settings
from test_workspace_http import calendar_client as calendar_client
from test_workspace_http import concurrent_engine as concurrent_engine
from test_workspace_http import live_client as live_client
from test_workspace_http import password_hash as password_hash
from test_workspace_http import settings as settings

from alembic import command


def test_nested_embeds_validate_ownership_preserve_missing_references_and_history(
    calendar_client: TestClient, concurrent_engine: Engine, password_hash: str
) -> None:
    database = create_database(calendar_client)
    view, foreign_view = (
        create_view(calendar_client, database),
        create_view(calendar_client, database),
    )
    body = {
        "schema_version": 1,
        "blocks": [
            {
                "id": str(uuid4()),
                "type": "toggle",
                "text": "Details",
                "children": [
                    {"id": str(uuid4()), "type": "text", "text": "Before"},
                    {
                        "id": str(uuid4()),
                        "type": "database_view",
                        "database_id": database["id"],
                        "view_id": view["id"],
                        "text": "Saved view",
                    },
                ],
            }
        ],
    }
    response = calendar_client.post(
        "/api/v1/notes/pages",
        headers=csrf_headers(calendar_client),
        json={"title": "Embedded", "document": body},
    )
    assert response.status_code == 201, response.text
    page = response.json()
    path = f"/api/v1/notes/pages/{page['id']}"
    assert (
        calendar_client.get(path).json()["document"]["blocks"][0]["children"][1]["view_id"]
        == view["id"]
    )
    assert (
        calendar_client.delete(
            view_path(database, view) + "?expected_version=1", headers=csrf_headers(calendar_client)
        ).status_code
        == 204
    )
    body["blocks"][0]["children"][0]["text"] = "After"
    saved = calendar_client.put(
        path + "/document",
        headers=csrf_headers(calendar_client),
        json={"expected_version": 1, "document": body},
    )
    assert (
        saved.status_code == 200
        and saved.json()["document"]["blocks"][0]["children"][0]["text"] == "After"
    )
    assert [item["version"] for item in calendar_client.get(path + "/revisions").json()] == [2, 1]
    rejected = calendar_client.post(
        "/api/v1/notes/pages",
        headers=csrf_headers(calendar_client),
        json={"title": "Missing view", "document": body},
    )
    assert rejected.status_code == 404
    with (
        concurrent_engine.begin() as connection,
        pytest.raises(RuntimeError, match="downgrade refused"),
    ):
        command.downgrade(migration_config(connection), "0047_database_calculations")
    seed_user(concurrent_engine, "other@example.com", password_hash)
    browser_login(calendar_client, "other@example.com")
    body["blocks"][0]["children"][1]["view_id"] = foreign_view["id"]
    denied = calendar_client.post(
        "/api/v1/notes/pages",
        headers=csrf_headers(calendar_client),
        json={"title": "Foreign view", "document": body},
    )
    assert denied.status_code == 404
    assert calendar_client.get("/api/v1/notes/pages").json()["items"] == []
