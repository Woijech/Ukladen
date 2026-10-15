from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, inspect
from sqlalchemy.orm import Session
from test_auth_http import browser_login, csrf_headers, seed_user
from test_auth_persistence import database_connection as database_connection
from test_auth_persistence import migration_config
from test_materials_http import BASE, upload
from test_materials_http import browser_settings as browser_settings
from test_materials_http import calendar_client as calendar_client
from test_materials_http import concurrent_engine as concurrent_engine
from test_materials_http import live_client as live_client
from test_materials_http import material_client as material_client
from test_materials_http import password_hash as password_hash
from test_materials_http import settings as settings
from test_notes_http import create_page

from alembic import command
from app.modules.materials.infrastructure.orm import MaterialModel
from app.modules.search.infrastructure.documents import SqlAlchemyMaterialTextIndex

SEARCH = "/api/v1/search"


def results(client: TestClient, q: str, **filters) -> list[dict]:
    response = client.get(SEARCH, params={"q": q} | filters)
    assert response.status_code == 200, response.text
    return response.json()["items"]


def index_material(engine: Engine, material: dict, body: str) -> None:
    with Session(engine) as database, database.begin():
        row = database.get(MaterialModel, UUID(material["id"]))
        assert row is not None
        SqlAlchemyMaterialTextIndex(database).put(row.user_id, row.id, body)
        row.status = "ready"


def test_current_pages_materials_and_language_search(
    material_client: TestClient, concurrent_engine: Engine
) -> None:
    page = create_page(material_client, title="Лекции", content="Students are running experiments")
    material = upload(material_client)
    index_material(
        concurrent_engine, material, "Лекция о базах данных. Students were running experiments."
    )
    assert {hit["id"] for hit in results(material_client, "run experiments")} == {
        page["id"],
        material["id"],
    }
    assert {hit["id"] for hit in results(material_client, "лекция")} == {page["id"], material["id"]}
    assert [hit["id"] for hit in results(material_client, "базы данных")] == [material["id"]]
    assert [hit["id"] for hit in results(material_client, "run", source="page")] == [page["id"]]
    assert [hit["id"] for hit in results(material_client, "run", extension="txt")] == [
        material["id"]
    ]
    assert results(material_client, "run", extension="pdf") == []
    assert len(results(material_client, "run", limit=1)) == 1
    assert len(results(material_client, "run", limit=1, offset=1)) == 1
    assert results(material_client, "run", offset=2) == []
    assert material_client.get(SEARCH, params={"q": "run"}).headers["cache-control"] == "no-store"


def test_block_content_updates_and_trash_are_immediately_effective(
    material_client: TestClient,
) -> None:
    page = create_page(material_client, title="Content")
    path = f"/api/v1/notes/pages/{page['id']}"
    changed = material_client.put(
        path + "/document",
        headers=csrf_headers(material_client),
        json={
            "expected_version": 1,
            "document": {
                "schema_version": 1,
                "blocks": [
                    {"id": str(uuid4()), "type": "heading", "text": "Thermodynamics", "level": 1},
                    {
                        "id": str(uuid4()),
                        "type": "list",
                        "style": "bulleted",
                        "items": ["entropy", "enthalpy"],
                    },
                    {
                        "id": str(uuid4()),
                        "type": "checkbox",
                        "text": "reversible process",
                        "checked": False,
                    },
                ],
            },
        },
    )
    assert changed.status_code == 200
    assert results(material_client, "entropy")[0]["id"] == page["id"]
    assert results(material_client, "reversible")[0]["version"] == 2
    assert (
        material_client.post(
            path + "/trash", headers=csrf_headers(material_client), json={"expected_version": 2}
        ).status_code
        == 200
    )
    assert results(material_client, "entropy") == []
    assert (
        material_client.post(
            path + "/restore", headers=csrf_headers(material_client), json={"expected_version": 3}
        ).status_code
        == 200
    )
    assert results(material_client, "entropy")[0]["id"] == page["id"]


def test_material_stale_index_trash_and_owner_isolation(
    material_client: TestClient, concurrent_engine: Engine, password_hash: str
) -> None:
    material = upload(material_client)
    index_material(concurrent_engine, material, "Private keywordquartz content")
    assert results(material_client, "keywordquartz")[0]["id"] == material["id"]
    path = f"{BASE}/{material['id']}"
    assert (
        material_client.post(
            path + "/trash", headers=csrf_headers(material_client), json={"expected_version": 2}
        ).status_code
        == 200
    )
    assert results(material_client, "keywordquartz") == []
    assert (
        material_client.post(
            path + "/restore", headers=csrf_headers(material_client), json={"expected_version": 3}
        ).status_code
        == 200
    )
    assert results(material_client, "keywordquartz")
    with Session(concurrent_engine) as database, database.begin():
        row = database.get(MaterialModel, UUID(material["id"]))
        assert row is not None
        row.status = "failed"
    assert results(material_client, "keywordquartz") == []
    seed_user(concurrent_engine, "other@example.com", password_hash)
    browser_login(material_client, "other@example.com")
    assert results(material_client, "lecture") == []
    material_client.cookies.clear()
    assert material_client.get(SEARCH, params={"q": "keywordquartz"}).status_code == 401


@pytest.mark.parametrize(
    "params",
    [
        {"q": " "},
        {"q": "x" * 201},
        {"q": "x", "limit": 51},
        {"q": "x", "offset": 1001},
        {"q": "x", "source": "page", "kind": "file"},
        {"q": "x", "kind": "link", "extension": "pdf"},
        {"q": "x", "source": "users"},
        {"q": "x", "extension": "exe"},
    ],
)
def test_bounded_search_input(material_client: TestClient, params: dict) -> None:
    assert material_client.get(SEARCH, params=params).status_code == 422


def test_search_migration_and_gin_indexes(database_connection: Connection) -> None:
    config = migration_config(database_connection)
    command.check(config)
    assert "ix_note_pages_search" in {
        item["name"] for item in inspect(database_connection).get_indexes("note_pages")
    }
    command.downgrade(config, "0019_materials")
    assert "search_material_documents" not in inspect(database_connection).get_table_names()
    command.upgrade(config, "head")
    command.check(config)
