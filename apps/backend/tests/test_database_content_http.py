from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import Engine, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_auth_http import browser_login, csrf_headers, seed_user
from test_databases_http import BASE, create_database
from test_logging import capture_json
from test_notes_http import change, create_page, lifecycle
from test_workspace_http import browser_settings as browser_settings
from test_workspace_http import calendar_client as calendar_client
from test_workspace_http import concurrent_engine as concurrent_engine
from test_workspace_http import live_client as live_client
from test_workspace_http import password_hash as password_hash
from test_workspace_http import settings as settings

from app.modules.notes.application.service import NoteService
from app.modules.notes.infrastructure.orm import PageModel
from app.modules.notes.infrastructure.repository import SqlAlchemyPageRepository
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication
from app.modules.workspace.application.database_content import DatabaseContentService
from app.modules.workspace.application.databases import DatabaseService
from app.modules.workspace.domain.organization import WorkspaceConflict
from app.modules.workspace.infrastructure.database_content import SqlAlchemyDatabaseContent
from app.modules.workspace.infrastructure.databases import SqlAlchemyDatabases
from app.modules.workspace.infrastructure.orm import DatabaseModel, DatabaseRecordModel


def schema_version(client: TestClient, database: dict) -> int:
    return client.get(f"{BASE}/{database['id']}").json()["schema_version"]


def create_property(client: TestClient, database: dict, kind: str = "text", **values) -> dict:
    response = client.post(
        f"{BASE}/{database['id']}/properties",
        headers=csrf_headers(client),
        json={
            "name": "Field",
            "kind": kind,
            "expected_schema_version": schema_version(client, database),
        }
        | values,
    )
    assert response.status_code == 201, response.text
    return response.json()["property"]


def create_record(client: TestClient, database: dict, **values) -> dict:
    payload = {"expected_schema_version": schema_version(client, database), "values": {}} | values
    if "page_id" not in payload and "title" not in payload:
        payload["title"] = "Record page"
    response = client.post(
        f"{BASE}/{database['id']}/records", headers=csrf_headers(client), json=payload
    )
    assert response.status_code == 201, response.text
    return response.json()


def property_change(client: TestClient, database: dict, definition: dict, **values):
    return client.patch(
        f"{BASE}/{database['id']}/properties/{definition['id']}",
        headers=csrf_headers(client),
        json={
            "expected_version": definition["version"],
            "expected_schema_version": schema_version(client, database),
        }
        | values,
    )


def record_path(database: dict, result: dict) -> str:
    return f"{BASE}/{database['id']}/records/{result['record']['id']}"


def test_records_share_page_body_and_keep_values_per_database(calendar_client: TestClient) -> None:
    first, second = create_database(calendar_client), create_database(calendar_client)
    page = create_page(calendar_client, content="Shared body")
    left, right = create_property(calendar_client, first), create_property(calendar_client, second)
    a = create_record(calendar_client, first, page_id=page["id"], values={left["id"]: "Left"})
    b = create_record(calendar_client, second, page_id=page["id"], values={right["id"]: "Right"})
    assert a["page"] == b["page"]
    assert all(value == page[key] for key, value in a["page"].items())
    assert a["record"]["id"] != b["record"]["id"] and "user_id" not in a["record"]
    assert "content" not in a["page"] and "document" not in a["page"]
    assert (
        calendar_client.post(
            f"{BASE}/{first['id']}/records",
            headers=csrf_headers(calendar_client),
            json={
                "page_id": page["id"],
                "expected_schema_version": schema_version(calendar_client, first),
            },
        ).status_code
        == 409
    )
    assert change(calendar_client, page, title="Renamed shared page").status_code == 200
    for db, record in ((first, a), (second, b)):
        assert (
            calendar_client.get(record_path(db, record)).json()["page"]["title"]
            == "Renamed shared page"
        )
    reverse = calendar_client.get(f"/api/v1/workspace/pages/{page['id']}/database-records")
    assert reverse.status_code == 200 and len(reverse.json()["items"]) == 2
    assert calendar_client.get(record_path(first, a)).json()["record"]["values"] == {
        left["id"]: "Left"
    }
    assert calendar_client.get(record_path(second, b)).json()["record"]["values"] == {
        right["id"]: "Right"
    }


def test_schema_versions_and_value_validation(calendar_client: TestClient) -> None:
    db = create_database(calendar_client)
    number = create_property(calendar_client, db, "number")
    checked = create_property(calendar_client, db, "checkbox")
    result = create_record(calendar_client, db, values={number["id"]: 0, checked["id"]: False})
    path = record_path(db, result)
    assert result["record"]["values"] == {number["id"]: 0, checked["id"]: False}
    for value in (True, "12", {"sql": "select 1"}):
        assert (
            calendar_client.patch(
                path,
                headers=csrf_headers(calendar_client),
                json={
                    "expected_version": 1,
                    "expected_schema_version": 3,
                    "values": {number["id"]: value},
                },
            ).status_code
            == 422
        )
    assert (
        property_change(calendar_client, db, number, name="Minutes", position=10).status_code == 200
    )
    assert (
        calendar_client.patch(
            path,
            headers=csrf_headers(calendar_client),
            json={
                "expected_version": 1,
                "expected_schema_version": 3,
                "values": {number["id"]: 12},
            },
        ).status_code
        == 409
    )
    changed = calendar_client.patch(
        path,
        headers=csrf_headers(calendar_client),
        json={
            "expected_version": 1,
            "expected_schema_version": 4,
            "values": {number["id"]: 12, checked["id"]: None},
        },
    )
    assert changed.status_code == 200 and changed.json()["record"]["values"] == {number["id"]: 12}
    assert (
        calendar_client.patch(
            path,
            headers=csrf_headers(calendar_client),
            json={
                "expected_version": 1,
                "expected_schema_version": 4,
                "values": {number["id"]: 13},
            },
        ).status_code
        == 409
    )
    assert (
        property_change(calendar_client, db, number, expected_version=2, kind="text").status_code
        == 409
    )
    assert calendar_client.get(path).json() == changed.json()
    assert (
        calendar_client.get(f"{BASE}/{db['id']}/properties").json()["items"][0]["id"]
        == checked["id"]
    )


def test_property_and_database_trash_preserve_independent_states(
    calendar_client: TestClient, concurrent_engine: Engine
) -> None:
    db = create_database(calendar_client)
    prop = create_property(calendar_client, db)
    other = create_property(calendar_client, db)
    first = create_record(calendar_client, db, values={prop["id"]: "Retained"})
    second = create_record(calendar_client, db)
    second_path, first_path = record_path(db, second), record_path(db, first)
    assert (
        calendar_client.post(
            second_path + "/trash",
            headers=csrf_headers(calendar_client),
            json={"expected_version": 1},
        ).status_code
        == 200
    )
    property_path = f"{BASE}/{db['id']}/properties/{prop['id']}"
    assert (
        calendar_client.post(
            property_path + "/trash",
            headers=csrf_headers(calendar_client),
            json={"expected_version": 1, "expected_schema_version": 3},
        ).status_code
        == 200
    )
    assert calendar_client.get(first_path).json()["record"]["values"] == {}
    changed = calendar_client.patch(
        first_path,
        headers=csrf_headers(calendar_client),
        json={"expected_version": 1, "expected_schema_version": 4, "values": {other["id"]: "New"}},
    )
    assert changed.status_code == 200
    with Session(concurrent_engine) as session:
        stored = session.get(DatabaseRecordModel, UUID(first["record"]["id"]))
        assert stored and stored.values[prop["id"]] == "Retained"
    current = calendar_client.get(f"{BASE}/{db['id']}").json()
    assert (
        calendar_client.post(
            f"{BASE}/{db['id']}/trash",
            headers=csrf_headers(calendar_client),
            json={"expected_version": current["version"]},
        ).status_code
        == 200
    )
    assert calendar_client.get(first_path).status_code == 409
    assert (
        calendar_client.post(
            f"{BASE}/{db['id']}/restore",
            headers=csrf_headers(calendar_client),
            json={"expected_version": current["version"] + 1},
        ).status_code
        == 200
    )
    assert len(calendar_client.get(f"{BASE}/{db['id']}/records").json()["items"]) == 1
    assert len(calendar_client.get(f"{BASE}/{db['id']}/records?trashed=true").json()["items"]) == 1
    assert (
        calendar_client.post(
            property_path + "/restore",
            headers=csrf_headers(calendar_client),
            json={"expected_version": 2, "expected_schema_version": 4},
        ).status_code
        == 200
    )
    assert calendar_client.get(first_path).json()["record"]["values"] == {
        prop["id"]: "Retained",
        other["id"]: "New",
    }
    assert (
        calendar_client.post(
            second_path + "/restore",
            headers=csrf_headers(calendar_client),
            json={"expected_version": 2},
        ).status_code
        == 200
    )
    assert (
        calendar_client.get(f"/api/v1/notes/pages/{first['record']['page_id']}").json()[
            "trashed_at"
        ]
        is None
    )


def test_select_conversion_validates_trashed_records_atomically(
    calendar_client: TestClient,
) -> None:
    db = create_database(calendar_client)
    prop = create_property(
        calendar_client, db, "select", options=[{"name": "Planned"}, {"name": "Done"}]
    )
    a, b = (item["id"] for item in prop["options"])
    first, second = (
        create_record(calendar_client, db, values={prop["id"]: identifier}) for identifier in (a, b)
    )
    second_path = record_path(db, second)
    assert (
        calendar_client.post(
            second_path + "/trash",
            headers=csrf_headers(calendar_client),
            json={"expected_version": 1},
        ).status_code
        == 200
    )
    assert (
        property_change(calendar_client, db, prop, options=[prop["options"][0]]).status_code == 409
    )
    renamed = property_change(
        calendar_client, db, prop, options=[{"id": a, "name": "Pending"}, prop["options"][1]]
    )
    assert renamed.status_code == 200
    converted = property_change(
        calendar_client, db, renamed.json()["property"], kind="multi_select"
    )
    assert converted.status_code == 200, converted.text
    first_path = record_path(db, first)
    current_first = calendar_client.get(first_path).json()
    current_second = calendar_client.get(second_path).json()
    assert current_first["record"]["values"][prop["id"]] == [a]
    assert current_first["record"]["version"] == 2 and current_second["record"]["version"] == 3
    assert current_second["record"]["values"][prop["id"]] == [b]
    assert (
        calendar_client.patch(
            first_path,
            headers=csrf_headers(calendar_client),
            json={
                "expected_version": 2,
                "expected_schema_version": converted.json()["schema_version"],
                "values": {prop["id"]: [a, b]},
            },
        ).status_code
        == 200
    )
    assert (
        property_change(
            calendar_client, db, converted.json()["property"], kind="select"
        ).status_code
        == 409
    )
    assert calendar_client.get(second_path).json() == current_second


def test_content_permissions_page_trash_and_csrf(
    calendar_client: TestClient, concurrent_engine: Engine, password_hash: str
) -> None:
    db = create_database(calendar_client)
    prop = create_property(calendar_client, db)
    page = create_page(calendar_client)
    record = create_record(calendar_client, db, page_id=page["id"])
    path = record_path(db, record)
    for method, route, body in (
        (
            "POST",
            f"{BASE}/{db['id']}/properties",
            {"name": "A", "kind": "text", "expected_schema_version": 2},
        ),
        ("POST", f"{BASE}/{db['id']}/records", {"title": "A", "expected_schema_version": 2}),
        (
            "PATCH",
            path,
            {"expected_version": 1, "expected_schema_version": 2, "values": {prop["id"]: "A"}},
        ),
        ("POST", path + "/trash", {"expected_version": 1}),
    ):
        assert calendar_client.request(method, route, json=body).status_code == 403
    assert lifecycle(calendar_client, page, "trash").status_code == 200
    assert calendar_client.get(path).json()["page"]["trashed_at"] is not None
    assert (
        calendar_client.patch(
            path,
            headers=csrf_headers(calendar_client),
            json={"expected_version": 1, "expected_schema_version": 2, "values": {prop["id"]: "A"}},
        ).status_code
        == 409
    )
    seed_user(concurrent_engine, "other@example.com", password_hash)
    browser_login(calendar_client, "other@example.com")
    for route in (
        path,
        f"{BASE}/{db['id']}/properties",
        f"{BASE}/{db['id']}/properties/{prop['id']}",
        f"/api/v1/workspace/pages/{page['id']}/database-records",
    ):
        assert calendar_client.get(route).status_code == 404
    owned = create_database(calendar_client)
    assert (
        calendar_client.post(
            f"{BASE}/{owned['id']}/records",
            headers=csrf_headers(calendar_client),
            json={"expected_schema_version": 1, "page_id": page["id"]},
        ).status_code
        == 404
    )
    assert (
        calendar_client.post(
            f"{BASE}/{db['id']}/properties",
            headers=csrf_headers(calendar_client),
            json={"name": "Foreign", "kind": "text", "expected_schema_version": 2},
        ).status_code
        == 404
    )


def test_failed_record_creation_rolls_back_new_page(calendar_client: TestClient) -> None:
    db = create_database(calendar_client)
    original = SqlAlchemyDatabaseContent.create_record

    def fail(self, record):
        original(self, record)
        raise SQLAlchemyError("private-record-values")

    with patch.object(SqlAlchemyDatabaseContent, "create_record", fail), capture_json() as output:
        result = calendar_client.post(
            f"{BASE}/{db['id']}/records",
            headers=csrf_headers(calendar_client),
            json={"expected_schema_version": 1, "title": "Private orphan"},
        )
    assert (
        result.status_code == 503
        and "private" not in result.text
        and "private-record-values" not in output.getvalue()
    )
    assert calendar_client.get("/api/v1/notes/pages").json()["items"] == []
    assert calendar_client.get(f"{BASE}/{db['id']}/records").json()["items"] == []


def test_concurrent_schema_changes_reject_stale_schema(
    calendar_client: TestClient, concurrent_engine: Engine
) -> None:
    db = create_database(calendar_client)
    owner = None
    with Session(concurrent_engine) as session:
        row = session.get(DatabaseModel, UUID(db["id"]))
        assert row
        owner = row.user_id

    def create(name: str) -> bool:
        try:
            with Session(concurrent_engine) as session, session.begin():
                notes = NoteService(
                    SqlAlchemyPageRepository(session), SqlAlchemyUserAuthentication(session)
                )
                service = DatabaseContentService(
                    SqlAlchemyDatabaseContent(session),
                    DatabaseService(SqlAlchemyDatabases(session), notes),
                )
                service.create_property(owner, UUID(db["id"]), 1, name, "text")
            return True
        except WorkspaceConflict:
            return False

    with ThreadPoolExecutor(2) as workers:
        assert sorted(workers.map(create, ["First", "Second"])) == [False, True]
    result = calendar_client.get(f"{BASE}/{db['id']}/properties").json()
    assert result["schema_version"] == 2 and len(result["items"]) == 1


def test_conversion_failure_rolls_back_all_versions_and_values(calendar_client: TestClient) -> None:
    db = create_database(calendar_client)
    prop = create_property(calendar_client, db, "select", options=[{"name": "Planned"}])
    records = [
        create_record(calendar_client, db, values={prop["id"]: prop["options"][0]["id"]})
        for _ in range(2)
    ]
    original = SqlAlchemyDatabaseContent.convert_values

    def fail(self, *args):
        original(self, *args)
        raise SQLAlchemyError("private-conversion-data")

    with patch.object(SqlAlchemyDatabaseContent, "convert_values", fail), capture_json() as output:
        response = property_change(calendar_client, db, prop, kind="multi_select")
    assert response.status_code == 503 and "private-conversion-data" not in output.getvalue()
    assert schema_version(calendar_client, db) == 2
    for record in records:
        assert calendar_client.get(record_path(db, record)).json() == record
    assert calendar_client.get(f"{BASE}/{db['id']}/properties/{prop['id']}").json() == prop


def test_record_and_page_read_use_one_snapshot(
    calendar_client: TestClient, concurrent_engine: Engine
) -> None:
    db = create_database(calendar_client)
    record = create_record(calendar_client, db)
    original = SqlAlchemyDatabaseContent.get_record

    def change_after_read(self, *args):
        result = original(self, *args)
        with Session(concurrent_engine) as writer, writer.begin():
            writer.execute(
                update(PageModel)
                .where(PageModel.id == UUID(record["page"]["id"]))
                .values(title="Concurrent title", version=2)
            )
        return result

    path = record_path(db, record)
    with patch.object(SqlAlchemyDatabaseContent, "get_record", change_after_read):
        assert calendar_client.get(path).json()["page"]["title"] == "Record page"
    assert calendar_client.get(path).json()["page"]["title"] == "Concurrent title"


def test_record_size_unknown_fields_and_versions_are_rejected(calendar_client: TestClient) -> None:
    db = create_database(calendar_client)
    fields = [create_property(calendar_client, db) for _ in range(5)]
    path = f"{BASE}/{db['id']}/records"
    for values in ({str(uuid4()): "Unknown"}, {field["id"]: "界" * 10000 for field in fields}):
        assert (
            calendar_client.post(
                path,
                headers=csrf_headers(calendar_client),
                json={"expected_schema_version": 6, "title": "Invalid record", "values": values},
            ).status_code
            == 422
        )
    for version in (None, True, "6"):
        assert (
            calendar_client.post(
                path,
                headers=csrf_headers(calendar_client),
                json={"expected_schema_version": version, "title": "Invalid record"},
            ).status_code
            == 422
        )
    assert calendar_client.get("/api/v1/notes/pages").json()["items"] == []
    assert calendar_client.get(path).json()["items"] == []
