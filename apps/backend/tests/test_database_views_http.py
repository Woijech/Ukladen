from datetime import UTC, datetime
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import Engine, update
from sqlalchemy.orm import Session
from test_auth_http import browser_login, csrf_headers, seed_user
from test_database_content_http import (
    create_property,
    create_record,
    property_change,
    record_path,
    schema_version,
)
from test_databases_http import BASE, create_database
from test_notes_http import lifecycle
from test_workspace_http import browser_settings as browser_settings
from test_workspace_http import calendar_client as calendar_client
from test_workspace_http import concurrent_engine as concurrent_engine
from test_workspace_http import live_client as live_client
from test_workspace_http import password_hash as password_hash
from test_workspace_http import settings as settings

from app.modules.notes.infrastructure.orm import PageModel
from app.modules.notes.infrastructure.repository import SqlAlchemyPageRepository


def create_view(client: TestClient, database: dict, **values) -> dict:
    response = client.post(
        f"{BASE}/{database['id']}/views",
        headers=csrf_headers(client),
        json={"name": "Table", "expected_schema_version": schema_version(client, database)}
        | values,
    )
    assert response.status_code == 201, response.text
    return response.json()


def view_path(database: dict, view: dict) -> str:
    return f"{BASE}/{database['id']}/views/{view['id']}"


def ids(response: dict) -> list[str]:
    return [item["record"]["id"] for item in response["items"]]


def test_table_columns_filters_sorting_and_live_values(calendar_client: TestClient) -> None:
    db = create_database(calendar_client)
    text, number = (
        create_property(calendar_client, db),
        create_property(calendar_client, db, "number"),
    )
    records = [
        create_record(
            calendar_client, db, values={text["id"]: f"Record {value}", number["id"]: value}
        )
        for value in (10, 30, 5)
    ]
    view = create_view(
        calendar_client,
        db,
        query={
            "columns": [number["id"], text["id"]],
            "filters": [{"property_id": number["id"], "operator": "gte", "value": 10}],
            "sorts": [{"property_id": number["id"], "direction": "desc"}],
        },
    )
    path = view_path(db, view)
    response = calendar_client.get(path + "/records?limit=1&offset=1")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == 2 and ids(data) == [records[0]["record"]["id"]]
    assert [item["id"] for item in data["properties"]] == [number["id"], text["id"]]
    assert "content" not in str(data["items"]) and response.headers["cache-control"] == "no-store"
    assert (
        calendar_client.patch(
            record_path(db, records[0]),
            headers=csrf_headers(calendar_client),
            json={
                "expected_version": 1,
                "expected_schema_version": 3,
                "values": {number["id"]: 40},
            },
        ).status_code
        == 200
    )
    assert ids(calendar_client.get(path + "/records").json()) == [
        records[0]["record"]["id"],
        records[1]["record"]["id"],
    ]
    renamed = property_change(calendar_client, db, number, name="Renamed")
    assert renamed.status_code == 200
    assert calendar_client.get(path + "/records").json()["properties"][0]["name"] == "Renamed"


def test_filter_semantics_keep_false_zero_unset_and_literal_text_distinct(
    calendar_client: TestClient,
) -> None:
    db = create_database(calendar_client)
    text, number, checked, dated = (
        create_property(calendar_client, db, kind)
        for kind in ("text", "number", "checkbox", "date")
    )
    selected = create_property(
        calendar_client, db, "select", options=[{"name": "Second"}, {"name": "First"}]
    )
    multi = create_property(calendar_client, db, "multi_select", options=[{"name": "Marked"}])
    a, b = (item["id"] for item in selected["options"])
    marker = multi["options"][0]["id"]
    first = create_record(
        calendar_client,
        db,
        values={
            text["id"]: "literal%_x",
            number["id"]: 0,
            checked["id"]: False,
            dated["id"]: {"kind": "date", "start": "2026-10-20"},
            selected["id"]: b,
            multi["id"]: [marker],
        },
    )
    second = create_record(
        calendar_client,
        db,
        values={
            text["id"]: "literalXXx",
            number["id"]: 2,
            checked["id"]: True,
            dated["id"]: {"kind": "date", "start": "2026-10-21"},
            selected["id"]: a,
        },
    )
    empty = create_record(calendar_client, db)
    timed = create_record(
        calendar_client,
        db,
        values={dated["id"]: {"kind": "datetime", "start": "2026-10-22T12:00:00Z"}},
    )
    cases = [
        (number, "eq", 0, [first]),
        (checked, "eq", False, [first]),
        (text, "contains", "%_", [first]),
        (text, "contains", "' OR true; --", []),
        (selected, "neq", b, [second, empty, timed]),
        (text, "is_empty", None, [empty, timed]),
        (checked, "is_not_empty", None, [first, second]),
        (multi, "contains", marker, [first]),
        (dated, "gt", {"kind": "date", "start": "2026-10-20"}, [second]),
    ]
    for prop, operator, value, expected in cases:
        view = create_view(
            calendar_client,
            db,
            query={"filters": [{"property_id": prop["id"], "operator": operator, "value": value}]},
        )
        response = calendar_client.get(view_path(db, view) + "/records")
        assert response.status_code == 200, response.text
        assert ids(response.json()) == [item["record"]["id"] for item in expected], (
            operator,
            response.text,
        )
    view = create_view(calendar_client, db, query={"sorts": [{"property_id": selected["id"]}]})
    assert ids(calendar_client.get(view_path(db, view) + "/records").json()) == [
        item["record"]["id"] for item in (second, first, empty, timed)
    ]


def test_page_trash_is_filtered_before_pagination_and_missing_filter_requires_repair(
    calendar_client: TestClient,
) -> None:
    db = create_database(calendar_client)
    prop = create_property(calendar_client, db)
    first, second, third = [
        create_record(calendar_client, db, values={prop["id"]: "Value"}) for _ in range(3)
    ]
    page = calendar_client.get(f"/api/v1/notes/pages/{first['page']['id']}").json()
    assert lifecycle(calendar_client, page, "trash").status_code == 200
    view = create_view(
        calendar_client,
        db,
        query={
            "columns": [],
            "filters": [{"property_id": prop["id"], "operator": "eq", "value": "Value"}],
        },
    )
    path = view_path(db, view)
    response = calendar_client.get(path + "/records?limit=1&offset=1").json()
    assert response["total"] == 2 and ids(response) == [third["record"]["id"]]
    assert response["properties"] == [] and response["items"][0]["record"]["values"] == {}
    assert (
        calendar_client.post(
            f"{BASE}/{db['id']}/properties/{prop['id']}/trash",
            headers=csrf_headers(calendar_client),
            json={"expected_version": 1, "expected_schema_version": 2},
        ).status_code
        == 200
    )
    assert calendar_client.get(path + "/records").status_code == 409
    assert calendar_client.get(path).json() == view
    repaired = calendar_client.patch(
        path,
        headers=csrf_headers(calendar_client),
        json={"expected_version": 1, "expected_schema_version": 3, "query": {}},
    )
    assert repaired.status_code == 200
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
    assert calendar_client.get(record_path(db, second)).status_code == 200


def test_table_view_authorization_csrf_and_bounded_configuration(
    calendar_client: TestClient, concurrent_engine: Engine, password_hash: str
) -> None:
    db = create_database(calendar_client)
    prop = create_property(calendar_client, db)
    view = create_view(calendar_client, db)
    path = view_path(db, view)
    for query in (
        {"version": True},
        {"sql": "select 1"},
        {"columns": [str(uuid4())]},
        {"columns": [prop["id"]] * 2},
        {"filters": [{"property_id": prop["id"], "operator": "gt", "value": "A"}]},
    ):
        assert (
            calendar_client.post(
                f"{BASE}/{db['id']}/views",
                headers=csrf_headers(calendar_client),
                json={"name": "Invalid", "expected_schema_version": 2, "query": query},
            ).status_code
            == 422
        )
    for method, route, body in (
        (
            "POST",
            f"{BASE}/{db['id']}/views",
            {"name": "Missing CSRF", "expected_schema_version": 2},
        ),
        (
            "PATCH",
            path,
            {"name": "Missing CSRF", "expected_version": 1, "expected_schema_version": 2},
        ),
        ("DELETE", path + "?expected_version=1", None),
    ):
        assert calendar_client.request(method, route, json=body).status_code == 403
    for query in ("limit=0", "limit=201", "offset=-1", "offset=2147483648"):
        assert calendar_client.get(path + "/records?" + query).status_code == 422
    seed_user(concurrent_engine, "other@example.com", password_hash)
    browser_login(calendar_client, "other@example.com")
    assert calendar_client.get(path).status_code == 404
    assert calendar_client.get(path + "/records").status_code == 404
    assert (
        calendar_client.delete(
            path + "?expected_version=1", headers=csrf_headers(calendar_client)
        ).status_code
        == 404
    )
    calendar_client.cookies.clear()
    assert calendar_client.get(path + "/records").status_code == 401


def test_table_bulk_page_metadata_uses_one_snapshot(
    calendar_client: TestClient, concurrent_engine: Engine
) -> None:
    db = create_database(calendar_client)
    record = create_record(calendar_client, db)
    view = create_view(calendar_client, db)
    original = SqlAlchemyPageRepository.summaries

    def trash_after_candidate_read(self, *args):
        with Session(concurrent_engine) as writer, writer.begin():
            writer.execute(
                update(PageModel)
                .where(PageModel.id == UUID(record["page"]["id"]))
                .values(trashed_at=datetime.now(UTC), trash_batch_id=UUID(record["page"]["id"]))
            )
        return original(self, *args)

    path = view_path(db, view) + "/records"
    with patch.object(SqlAlchemyPageRepository, "summaries", trash_after_candidate_read):
        response = calendar_client.get(path)
        assert response.status_code == 200, response.text
        assert response.json()["total"] == 1
    assert calendar_client.get(path).json()["total"] == 0
