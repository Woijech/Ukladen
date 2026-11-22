from copy import deepcopy
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import Engine
from test_auth_http import browser_login, csrf_headers, seed_user
from test_database_content_http import create_property, create_record
from test_database_views_http import create_view
from test_databases_http import create_database
from test_workspace_http import browser_settings as browser_settings
from test_workspace_http import calendar_client as calendar_client
from test_workspace_http import concurrent_engine as concurrent_engine
from test_workspace_http import live_client as live_client
from test_workspace_http import password_hash as password_hash
from test_workspace_http import settings as settings

from app.modules.workspace.infrastructure.transfer import SqlAlchemyTransferReceipts

BASE = "/api/v1/workspace/transfer"
PAGES = "/api/v1/notes/pages"
DBS = "/api/v1/workspace/databases"


def post(client: TestClient, path: str, payload: dict):
    return client.post(path, headers=csrf_headers(client), json=payload)


def test_portable_roundtrip_rewrites_typed_refs_preserves_text_trash_and_owner(
    calendar_client: TestClient, concurrent_engine: Engine, password_hash: str
) -> None:
    client = calendar_client
    target = create_database(client, name="Inputs")
    amount = create_property(client, target, "number", name="Amount")
    target_record = create_record(client, target, title="Input", values={amount["id"]: 7})
    source = create_database(client, name="Summary")
    numeric = create_property(client, source, "number", name="Days")
    relation = create_property(
        client, source, "relation", name="Sources", relation_database_id=target["id"]
    )
    formula = create_property(
        client,
        source,
        "formula",
        name="Twice",
        calculation={"expression": f'prop("{numeric["id"]}") * 2'},
    )
    rollup = create_property(
        client,
        source,
        "rollup",
        name="Total",
        calculation={
            "relation_property_id": relation["id"],
            "value_property_id": amount["id"],
            "operation": "sum",
        },
    )
    create_record(
        client,
        source,
        title="Summary",
        values={numeric["id"]: 3, relation["id"]: [target_record["record"]["id"]]},
    )
    view = create_view(client, source)
    literal = f"Keep literal UUID {source['id']} and https://example.com/{view['id']}"
    page = post(
        client,
        PAGES,
        {
            "title": "Tree",
            "document": {
                "schema_version": 1,
                "blocks": [
                    {
                        "id": str(uuid4()),
                        "type": "toggle",
                        "text": "Details",
                        "children": [
                            {"id": str(uuid4()), "type": "text", "text": literal},
                            {
                                "id": str(uuid4()),
                                "type": "database_view",
                                "database_id": source["id"],
                                "view_id": view["id"],
                                "text": "Summary view",
                            },
                        ],
                    }
                ],
            },
        },
    ).json()
    child = post(client, PAGES, {"title": "Independent trash", "parent_id": page["id"]}).json()
    assert post(client, f"{PAGES}/{child['id']}/trash", {"expected_version": 1}).status_code == 200
    assert post(client, f"{PAGES}/{page['id']}/trash", {"expected_version": 1}).status_code == 200
    exported = client.get(BASE + "/export")
    assert exported.status_code == 200, exported.text
    raw = exported.json()
    assert "user_id" not in raw["archive"]
    assert len(raw["archive"]["pages"]) == 4
    assert next(db for db in raw["archive"]["databases"] if db["id"] == source["id"])["records"][0][
        "values"
    ] == {numeric["id"]: 3, relation["id"]: [target_record["record"]["id"]]}
    seed_user(concurrent_engine, "importer@example.com", password_hash)
    browser_login(client, "importer@example.com")
    payload = raw | {"title": "Imported"}
    preview = post(client, BASE + "/preview", payload)
    assert preview.status_code == 200, preview.text
    assert client.get(PAGES).json()["items"] == []
    assert client.get(DBS).json()["items"] == []
    payload["digest"] = preview.json()["digest"]
    applied = post(client, BASE + "/import", payload)
    assert applied.status_code == 200, applied.text
    assert post(client, BASE + "/import", payload).json() == applied.json()
    result = client.get(BASE + "/export").json()["archive"]
    assert len(result["pages"]) == 5 and len(result["databases"]) == 2
    copied_db = next(db for db in result["databases"] if db["name"] == "Summary")
    assert copied_db["id"] != source["id"]
    copied_properties = {p["name"]: p for p in copied_db["properties"]}
    assert copied_properties["Twice"]["id"] != formula["id"]
    assert (
        copied_properties["Days"]["id"] in copied_properties["Twice"]["calculation"]["expression"]
    )
    assert copied_properties["Total"]["id"] != rollup["id"]
    copied_record = client.get(f"{DBS}/{copied_db['id']}/records").json()["items"][0]
    assert copied_record["record"]["values"][copied_properties["Twice"]["id"]] == 6
    assert copied_record["record"]["values"][copied_properties["Total"]["id"]] == 7
    tree = next(p for p in result["pages"] if p["title"] == "Tree")
    nested = tree["document"]["blocks"][0]["children"]
    assert nested[0]["text"] == literal
    assert nested[1]["database_id"] == copied_db["id"]
    assert nested[1]["view_id"] == copied_db["views"][0]["id"]
    assert tree["trash_batch_id"] == tree["id"]
    independent = next(p for p in result["pages"] if p["title"] == "Independent trash")
    assert independent["trash_batch_id"] == independent["id"]
    assert client.get(f"{PAGES}/{page['id']}").status_code == 404


def test_preview_import_validation_csrf_digest_and_atomic_failure(
    calendar_client: TestClient,
) -> None:
    client = calendar_client
    page = post(client, PAGES, {"title": "Original", "content": "Keep me"}).json()
    raw = client.get(BASE + "/export").json()
    payload = raw | {"title": "Imported"}
    assert client.post(BASE + "/preview", json=payload).status_code == 403
    assert post(client, BASE + "/import", payload).status_code == 409
    broken = deepcopy(payload)
    broken["archive"]["pages"][0]["parent_id"] = page["id"]
    assert post(client, BASE + "/preview", broken).status_code == 422
    broken = deepcopy(payload)
    broken["archive"]["pages"][0]["user_id"] = str(uuid4())
    assert post(client, BASE + "/preview", broken).status_code == 422
    preview = post(client, BASE + "/preview", payload)
    assert preview.status_code == 200, preview.text
    payload["digest"] = preview.json()["digest"]
    changed = payload | {"title": "Changed"}
    assert post(client, BASE + "/import", changed).status_code == 409
    with patch.object(SqlAlchemyTransferReceipts, "save", side_effect=ValueError("private")):
        failed = post(client, BASE + "/import", payload)
    assert failed.status_code == 422 and "private" not in failed.text
    assert [p["id"] for p in client.get(PAGES).json()["items"]] == [page["id"]]
    assert post(client, BASE + "/import", payload).status_code == 200


def test_missing_embed_fails_preview_without_partial_import(calendar_client: TestClient) -> None:
    client = calendar_client
    payload = {
        "title": "Import",
        "archive": {
            "format": "ukladen.pages-databases",
            "version": 1,
            "databases": [],
            "pages": [
                {
                    "id": str(uuid4()),
                    "parent_id": None,
                    "title": "Page",
                    "trash_batch_id": None,
                    "document": {
                        "schema_version": 1,
                        "blocks": [
                            {
                                "id": str(uuid4()),
                                "type": "database_view",
                                "database_id": str(uuid4()),
                                "view_id": str(uuid4()),
                            }
                        ],
                    },
                }
            ],
        },
    }
    response = post(client, BASE + "/preview", payload)
    assert response.status_code == 422, response.text
    assert client.get(PAGES).json()["items"] == []


def test_retained_hidden_values_and_trashed_relation_targets_roundtrip(
    calendar_client: TestClient,
) -> None:
    client = calendar_client
    db = create_database(client)
    number = create_property(client, db, "number")
    relation = create_property(client, db, "relation", relation_database_id=db["id"])
    target = create_record(client, db, title="Retained target", values={number["id"]: 19})
    source = create_record(
        client,
        db,
        title="Retained source",
        values={relation["id"]: [target["record"]["id"]], number["id"]: 23},
    )
    assert (
        post(
            client,
            f"{DBS}/{db['id']}/records/{target['record']['id']}/trash",
            {"expected_version": 1},
        ).status_code
        == 200
    )
    schema = client.get(f"{DBS}/{db['id']}").json()["schema_version"]
    assert (
        post(
            client,
            f"{DBS}/{db['id']}/properties/{number['id']}/trash",
            {"expected_version": 1, "expected_schema_version": schema},
        ).status_code
        == 200
    )
    raw = client.get(BASE + "/export").json()
    retained = raw["archive"]["databases"][0]
    assert (
        next(r for r in retained["records"] if r["id"] == source["record"]["id"])["values"][
            number["id"]
        ]
        == 23
    )
    payload = raw | {"title": "Retained copy"}
    preview = post(client, BASE + "/preview", payload)
    assert preview.status_code == 200, preview.text
    payload["digest"] = preview.json()["digest"]
    assert post(client, BASE + "/import", payload).status_code == 200
    copies = client.get(BASE + "/export").json()["archive"]["databases"]
    copied = next(d for d in copies if d["id"] != db["id"])
    copied_number = next(p for p in copied["properties"] if p["kind"] == "number")
    assert copied_number["trashed"]
    assert sorted(r["values"][copied_number["id"]] for r in copied["records"]) == [19, 23]
    assert sum(r["trashed"] for r in copied["records"]) == 1
