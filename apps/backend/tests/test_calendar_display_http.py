from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, update
from sqlalchemy.orm import Session
from test_auth_http import browser_login, csrf_headers, seed_user
from test_calendar_http import create_event
from test_calendar_http import enrolled as enrolled
from test_database_calendar_http import calendar_view
from test_database_content_http import create_property, create_record
from test_database_views_http import create_view
from test_databases_http import create_database
from test_schedule_expansion import schedule_fixture
from test_schedule_storage import store as store
from test_workspace_http import browser_settings as browser_settings
from test_workspace_http import calendar_client as calendar_client
from test_workspace_http import concurrent_engine as concurrent_engine
from test_workspace_http import live_client as live_client
from test_workspace_http import password_hash as password_hash
from test_workspace_http import settings as settings

from app.modules.academics.infrastructure.orm import AcademicProfileModel
from app.modules.notes.infrastructure.orm import PageModel
from app.modules.schedule.application.expansion import expand_schedule
from app.modules.schedule.infrastructure.storage import SqlAlchemyScheduleStore
from app.modules.workspace.infrastructure.database_views import SqlAlchemyDatabaseViews

DATES = "?date_from=2026-10-01&date_to=2026-10-31"
BASE = "/api/v1/calendar/display" + DATES


def setup_views(client):
    db = create_database(client)
    a, b = create_property(client, db, "date"), create_property(client, db, "date")
    record = create_record(
        client,
        db,
        values={
            a["id"]: {"kind": "date", "start": "2026-10-07"},
            b["id"]: {"kind": "datetime", "start": "2026-10-08T12:00:00+03:00"},
        },
    )
    return db, record, [calendar_view(client, db, prop) for prop in (a, a, b)]


def test_mixed_display_deduplicates_record_property_identity_without_copying_events(
    calendar_client: TestClient,
):
    client = calendar_client
    event = create_event(client)
    db, record, views = setup_views(client)
    path = BASE + "".join(f"&database_view_ids={view['id']}" for view in views)
    response = client.get(path)
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result["entries"]) == 3
    normal = client.get("/api/v1/calendar/events" + DATES).json()
    assert result["entries"][0] == normal["events"][0]
    assert result["entries"][0]["source_event_id"] == event["id"]
    assert result["source"] == normal["source"] and result["warnings"] == normal["warnings"]
    assert len({item["id"] for item in result["entries"]}) == 3
    assert all(
        item["record_id"] == record["record"]["id"] and item["blocks_time"] is False
        for item in result["entries"][1:]
    )
    assert len(client.get("/api/v1/calendar/events" + DATES).json()["events"]) == 1
    assert client.get(BASE).json()["entries"] == normal["events"]
    assert client.get(BASE + "&source=official").json()["entries"] == []
    client.delete(
        f"/api/v1/workspace/databases/{db['id']}/views/{views[0]['id']}?expected_version=1",
        headers=csrf_headers(client),
    )
    assert client.get(path).status_code == 404  # Never silently drop a requested missing source.
    assert response.headers["cache-control"] == "no-store"


def test_mixed_display_preserves_official_overrides_source_state_and_warnings(
    enrolled: TestClient, store: SqlAlchemyScheduleStore, concurrent_engine: Engine
):
    client = enrolled
    snapshot, now = schedule_fixture(), datetime.now(UTC)
    lesson = replace(expand_schedule(snapshot)[0], subgroup=1)
    token = store.claim(24066, "353501", now)
    assert token and store.apply(24066, token, snapshot, [lesson], now)
    create_event(client)
    _, _, views = setup_views(client)
    assert (
        client.put(
            f"/api/v1/calendar/overrides/{lesson.id}",
            headers=csrf_headers(client),
            json={
                "hidden": True,
                "starts_at": "2026-10-07T15:00:00Z",
                "ends_at": "2026-10-07T16:00:00Z",
            },
        ).status_code
        == 200
    )
    path = BASE + f"&database_view_ids={views[0]['id']}"
    assert [item["source"] for item in client.get(path).json()["entries"]] == [
        "personal",
        "record_date",
    ]
    token = store.claim(24066, "353501", now + timedelta(hours=2))
    assert token
    store.fail(24066, token, "source_unavailable", now + timedelta(hours=2))
    result = client.get(path + "&include_hidden=true").json()
    normal = client.get("/api/v1/calendar/events" + DATES + "&include_hidden=true").json()
    assert result["entries"][:-1] == normal["events"]
    assert result["source"] == normal["source"] and result["warnings"] == normal["warnings"]
    assert "schedule_error" in result["warnings"]
    official = next(item for item in result["entries"] if item["source"] == "official")
    assert official["hidden"] and official["blocks_time"] and official["has_override"]
    with Session(concurrent_engine) as writer, writer.begin():
        writer.execute(delete(AcademicProfileModel))
    result = client.get(path).json()
    assert [item["source"] for item in result["entries"]] == ["personal", "record_date"]
    assert "academic_profile_not_selected" in result["warnings"]


def test_mixed_display_source_selection_is_bounded_and_owned(
    calendar_client: TestClient, concurrent_engine: Engine, password_hash: str
):
    client = calendar_client
    db, _, views = setup_views(client)
    for identifiers in ([views[0]["id"]] * 2, [str(uuid4()) for _ in range(21)]):
        assert (
            client.get(
                BASE + "".join(f"&database_view_ids={item}" for item in identifiers)
            ).status_code
            == 422
        )
    table = create_view(client, db)
    assert client.get(BASE + f"&database_view_ids={table['id']}").status_code == 409
    seed_user(concurrent_engine, "other@example.com", password_hash)
    browser_login(client, "other@example.com")
    assert client.get(BASE + f"&database_view_ids={views[0]['id']}").status_code == 404
    client.cookies.clear()
    assert client.get(BASE).status_code == 401


def test_mixed_display_keeps_one_snapshot_for_event_and_record_sources(
    calendar_client: TestClient, concurrent_engine: Engine
):
    client = calendar_client
    create_event(client)
    _, record, views = setup_views(client)
    original = SqlAlchemyDatabaseViews.get_owned

    def change_page(self, *args):
        with Session(concurrent_engine) as writer, writer.begin():
            writer.execute(
                update(PageModel)
                .where(PageModel.id == UUID(record["page"]["id"]))
                .values(title="After snapshot")
            )
        return original(self, *args)

    path = BASE + f"&database_view_ids={views[0]['id']}"
    with patch.object(SqlAlchemyDatabaseViews, "get_owned", change_page):
        response = client.get(path)
        assert response.status_code == 200, response.text
        assert response.json()["entries"][-1]["title"] == record["page"]["title"]
    assert client.get(path).json()["entries"][-1]["title"] == "After snapshot"
