from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import Engine
from test_auth_http import browser_login, csrf_headers, seed_user
from test_database_content_http import create_property, create_record, record_path, schema_version
from test_database_views_http import create_view, view_path
from test_databases_http import BASE, create_database
from test_notes_http import lifecycle
from test_workspace_http import browser_settings as browser_settings
from test_workspace_http import calendar_client as calendar_client
from test_workspace_http import concurrent_engine as concurrent_engine
from test_workspace_http import live_client as live_client
from test_workspace_http import password_hash as password_hash
from test_workspace_http import settings as settings


def entries_path(db, view, day="2026-10-25"):
    return view_path(db, view) + f"/entries?date_from={day}&date_to={day}"


def calendar_view(client, db, prop, **values):
    return create_view(client, db, layout="calendar", date_property_id=prop["id"], **values)


def test_date_projection_preserves_date_kind_and_timezone_overlap(calendar_client: TestClient):
    client = calendar_client
    assert (
        client.patch(
            "/api/v1/users/me", headers=csrf_headers(client), json={"timezone": "Europe/Berlin"}
        ).status_code
        == 200
    )
    db = create_database(client)
    prop = create_property(client, db, "date")
    payloads = [
        {"kind": "date", "start": "2026-10-25"},
        {"kind": "date", "start": "2026-10-24", "end": "2026-10-25"},
        {"kind": "datetime", "start": "2026-10-24T22:00:00Z"},
        {"kind": "datetime", "start": "2026-10-25T22:59:59Z"},
        {"kind": "datetime", "start": "2026-10-24T20:00:00Z", "end": "2026-10-24T22:00:01Z"},
        {"kind": "datetime", "start": "2026-10-24T20:00:00Z", "end": "2026-10-24T22:00:00Z"},
        {"kind": "datetime", "start": "2026-10-25T23:00:00Z"},
        {"kind": "date", "start": "2026-10-26"},
    ]
    records = [create_record(client, db, values={prop["id"]: value}) for value in payloads]
    create_record(client, db)  # Undated rows remain in the table, not in the calendar.
    view = calendar_view(client, db, prop, calendar_layout="month")
    response = client.get(entries_path(db, view))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["timezone"] == "Europe/Berlin" and result["view"]["calendar_layout"] == "month"
    assert [item["record_id"] for item in result["entries"]] == [
        r["record"]["id"] for r in records[:5]
    ]
    assert result["entries"][0]["date"] == {"kind": "date", "start": "2026-10-25", "end": None}
    assert all(
        item["blocks_time"] is False and item["source"] == "record_date"
        for item in result["entries"]
    )
    assert "content" not in response.text and response.headers["cache-control"] == "no-store"
    assert client.get(view_path(db, view) + "/records").status_code == 409
    assert client.get(entries_path(db, view, "2026-10-25T00:00:00Z")).status_code == 422
    assert (
        client.get(
            view_path(db, view) + "/entries?date_from=2026-10-25&date_to=2027-10-26"
        ).status_code
        == 422
    )


def test_calendar_binding_filters_and_trash_require_explicit_repair(calendar_client: TestClient):
    client = calendar_client
    db = create_database(client)
    prop, text = create_property(client, db, "date"), create_property(client, db)
    records = [
        create_record(
            client,
            db,
            values={prop["id"]: {"kind": "date", "start": "2026-10-25"}, text["id"]: name},
        )
        for name in ("Show", "Hide", "Show")
    ]
    view = calendar_view(
        client,
        db,
        prop,
        query={"filters": [{"property_id": text["id"], "operator": "eq", "value": "Show"}]},
    )
    page = client.get(f"/api/v1/notes/pages/{records[2]['page']['id']}").json()
    assert lifecycle(client, page, "trash").status_code == 200
    assert [item["record_id"] for item in client.get(entries_path(db, view)).json()["entries"]] == [
        records[0]["record"]["id"]
    ]
    assert (
        client.post(
            f"{BASE}/{db['id']}/properties/{prop['id']}/trash",
            headers=csrf_headers(client),
            json={"expected_version": 1, "expected_schema_version": 3},
        ).status_code
        == 200
    )
    assert client.get(entries_path(db, view)).status_code == 409
    replacement = create_property(client, db, "date")
    repaired = client.patch(
        view_path(db, view),
        headers=csrf_headers(client),
        json={
            "expected_version": 1,
            "expected_schema_version": schema_version(client, db),
            "date_property_id": replacement["id"],
        },
    )
    assert repaired.status_code == 200, repaired.text
    assert client.get(entries_path(db, view)).json()["entries"] == []
    for binding in (None, text["id"], str(uuid4())):
        response = client.post(
            f"{BASE}/{db['id']}/views",
            headers=csrf_headers(client),
            json={
                "name": "Invalid",
                "layout": "calendar",
                "date_property_id": binding,
                "expected_schema_version": schema_version(client, db),
            },
        )
        assert response.status_code == 422
    assert (
        client.patch(
            view_path(db, view),
            headers=csrf_headers(client),
            json={
                "expected_version": 2,
                "expected_schema_version": schema_version(client, db),
                "layout": "table",
            },
        ).status_code
        == 422
    )


def test_moving_date_checks_record_schema_and_binding_versions(calendar_client: TestClient):
    client = calendar_client
    db = create_database(client)
    a, b = create_property(client, db, "date"), create_property(client, db, "date")
    record = create_record(client, db, values={a["id"]: {"kind": "date", "start": "2026-10-25"}})
    view = calendar_view(client, db, a)
    path = view_path(db, view) + f"/entries/{record['record']['id']}"
    body = {
        "property_id": a["id"],
        "expected_version": 1,
        "expected_schema_version": 3,
        "date": {"kind": "date", "start": "2026-10-26"},
    }
    page_before = client.get(f"/api/v1/notes/pages/{record['page']['id']}").json()
    assert client.patch(path, json=body).status_code == 403
    for changes in (
        {"expected_version": 2},
        {"expected_schema_version": 2},
        {"property_id": b["id"]},
    ):
        assert (
            client.patch(path, headers=csrf_headers(client), json=body | changes).status_code == 409
        )
    response = client.patch(path, headers=csrf_headers(client), json=body)
    assert response.status_code == 200, response.text
    assert response.json()["record"]["values"][a["id"]]["start"] == "2026-10-26"
    assert client.get(f"/api/v1/notes/pages/{record['page']['id']}").json() == page_before
    assert client.get(entries_path(db, view)).json()["entries"] == []
    assert (
        client.get(entries_path(db, view, "2026-10-26")).json()["entries"][0]["record_version"] == 2
    )
    assert (
        client.patch(
            view_path(db, view),
            headers=csrf_headers(client),
            json={"expected_version": 1, "expected_schema_version": 3, "date_property_id": b["id"]},
        ).status_code
        == 200
    )
    assert (
        client.patch(
            path, headers=csrf_headers(client), json=body | {"expected_version": 2}
        ).status_code
        == 409
    )
    assert client.get(record_path(db, record)).json()["record"]["version"] == 2


def test_calendar_view_ownership_and_parent_trash(
    calendar_client: TestClient, concurrent_engine: Engine, password_hash: str
):
    client = calendar_client
    db = create_database(client)
    prop = create_property(client, db, "date")
    record = create_record(client, db)
    view = calendar_view(client, db, prop)
    current = client.get(f"{BASE}/{db['id']}").json()
    assert (
        client.post(
            f"{BASE}/{db['id']}/trash",
            headers=csrf_headers(client),
            json={"expected_version": current["version"]},
        ).status_code
        == 200
    )
    assert client.get(entries_path(db, view)).status_code == 409
    assert (
        client.post(
            f"{BASE}/{db['id']}/restore",
            headers=csrf_headers(client),
            json={"expected_version": current["version"] + 1},
        ).status_code
        == 200
    )
    seed_user(concurrent_engine, "other@example.com", password_hash)
    browser_login(client, "other@example.com")
    assert client.get(entries_path(db, view)).status_code == 404
    assert (
        client.patch(
            view_path(db, view) + f"/entries/{record['record']['id']}",
            headers=csrf_headers(client),
            json={
                "property_id": prop["id"],
                "expected_version": 1,
                "expected_schema_version": 2,
                "date": {"kind": "date", "start": "2026-10-25"},
            },
        ).status_code
        == 404
    )
