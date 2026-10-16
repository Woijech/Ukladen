from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_auth_http import browser_login, csrf_headers, seed_user
from test_calendar_http import PAYLOAD, create_event
from test_calendar_http import enrolled as enrolled
from test_calendar_http import store as store
from test_logging import capture_json, entries
from test_notes_http import create_page
from test_schedule_expansion import schedule_fixture
from test_workspace_http import browser_settings as browser_settings
from test_workspace_http import calendar_client as calendar_client
from test_workspace_http import concurrent_engine as concurrent_engine
from test_workspace_http import create_organization
from test_workspace_http import live_client as live_client
from test_workspace_http import password_hash as password_hash
from test_workspace_http import settings as settings
from test_workspace_memberships_http import members, put

from app.modules.academics.infrastructure.orm import AcademicProfileModel
from app.modules.schedule.application.expansion import expand_schedule
from app.modules.schedule.infrastructure.storage import SqlAlchemyScheduleStore
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication
from app.modules.workspace.application.calendar_views import CalendarViewService
from app.modules.workspace.application.service import WorkspaceService
from app.modules.workspace.domain.organization import WorkspaceConflict
from app.modules.workspace.infrastructure.calendar_views import SqlAlchemyCalendarViews
from app.modules.workspace.infrastructure.orm import CalendarViewModel, MembershipModel
from app.modules.workspace.infrastructure.repository import (
    SqlAlchemyMemberships,
    SqlAlchemyOrganizations,
)

BASE = "/api/v1/workspace/calendar-views"
DATES = "?date_from=2026-09-01&date_to=2026-10-31"


def create_view(client: TestClient, **values) -> dict:
    response = client.post(BASE, headers=csrf_headers(client), json={"name": "Study"} | values)
    assert response.status_code == 201, response.text
    return response.json()


def test_view_crud_versions_pagination_and_preservation(calendar_client: TestClient) -> None:
    event, page = create_event(calendar_client), create_page(calendar_client)
    collection = create_organization(calendar_client)
    put(calendar_client, members(collection), "personal", event["id"])
    with capture_json() as output:
        view = create_view(calendar_client, name=" Private view ", color="#Aa00FF")
        path = f"{BASE}/{view['id']}"
        assert view["name"] == "Private view" and view["color"] == "#aa00ff"
        assert view["layout"] == "week" and view["sort_order"] == "asc"
        assert view["version"] == 1 and not view["include_hidden"] and "user_id" not in view
        assert calendar_client.get(path).json() == view
        assert calendar_client.get(BASE).json()["items"] == [view]
        assert calendar_client.get(BASE + "?limit=1&offset=1").json()["items"] == []
        response = calendar_client.get(path + "/events" + DATES)
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        assert response.json()["events"][0]["source_event_id"] == event["id"]
        assert response.json()["warnings"] == ["academic_profile_not_selected"]
        changed = calendar_client.patch(
            path,
            headers=csrf_headers(calendar_client),
            json={
                "expected_version": 1,
                "name": "Changed",
                "color": None,
                "layout": "month",
            },
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["version"] == 2 and changed.json()["color"] is None
        assert changed.json()["sources"] == view["sources"]
        for method, suffix, payload in (
            ("PATCH", "", {"expected_version": 1, "name": "Stale"}),
            ("DELETE", "?expected_version=1", None),
        ):
            assert (
                calendar_client.request(
                    method, path + suffix, headers=csrf_headers(calendar_client), json=payload
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
    assert view["id"] not in output.getvalue() and "Private view" not in output.getvalue()
    assert any(row["event"] == "workspace.calendar_view_deleted" for row in entries(output))
    assert calendar_client.get(f"/api/v1/calendar/personal-events/{event['id']}").json() == event
    assert calendar_client.get(f"/api/v1/notes/pages/{page['id']}").json() == page
    assert len(calendar_client.get(members(collection)).json()["items"]) == 1


@pytest.mark.parametrize(
    "values",
    [
        {"name": " "},
        {"color": "red"},
        {"name": "a\x00b"},
        {"user_id": str(uuid4())},
        {"sources": []},
        {"sources": None},
        {"sources": [{"source": "page"}]},
        {"sources": [{"source": "personal"}, {"source": "personal"}]},
        {"sources": [{"source": "personal", "tag_ids": ["invalid"]}]},
        {"sources": [{"source": "personal", "collection_ids": [str(uuid4())] * 2}]},
        {"sources": [{"source": "personal", "tag_ids": [str(uuid4()) for _ in range(21)]}]},
        {"sources": [{"source": "personal", "sql": "select 1"}]},
        {"layout": "board"},
        {"sort_order": "random"},
        {"include_hidden": 1},
    ],
)
def test_invalid_view_definitions(calendar_client: TestClient, values: dict) -> None:
    assert (
        calendar_client.post(
            BASE, headers=csrf_headers(calendar_client), json={"name": "Study"} | values
        ).status_code
        == 422
    )
    assert calendar_client.get(BASE).json()["items"] == []


def test_patch_and_range_validation(calendar_client: TestClient) -> None:
    view = create_view(calendar_client)
    path = f"{BASE}/{view['id']}"
    for changes in (
        {},
        {"name": None},
        {"sources": None},
        {"sources": []},
        {"layout": None},
        {"sort_order": None},
        {"include_hidden": None},
        {"unexpected": True},
    ):
        assert (
            calendar_client.patch(
                path, headers=csrf_headers(calendar_client), json={"expected_version": 1} | changes
            ).status_code
            == 422
        )
    for query in (
        "",
        "?date_from=2026-10-07",
        "?date_from=2026-10-08&date_to=2026-10-07",
        "?date_from=2025-01-01&date_to=2026-10-07",
        "?date_from=2026-10-07T00:00:00Z&date_to=2026-10-08",
    ):
        assert calendar_client.get(path + "/events" + query).status_code == 422
    for query in ("limit=0", "limit=201", "offset=-1", "offset=2147483648"):
        assert calendar_client.get(BASE + "?" + query).status_code == 422
    assert calendar_client.get(path).json() == view


def test_owner_csrf_and_filter_reference_validation(
    calendar_client: TestClient, concurrent_engine: Engine, password_hash: str
) -> None:
    collection = create_organization(calendar_client)
    view = create_view(calendar_client)
    path = f"{BASE}/{view['id']}"
    for method, route, payload in (
        ("POST", BASE, {"name": "No CSRF"}),
        ("PATCH", path, {"expected_version": 1, "name": "No CSRF"}),
        ("DELETE", path + "?expected_version=1", None),
    ):
        assert calendar_client.request(method, route, json=payload).status_code == 403
    for source in (
        {"source": "personal", "tag_ids": [collection["id"]]},
        {"source": "personal", "collection_ids": [str(uuid4())]},
    ):
        assert (
            calendar_client.post(
                BASE,
                headers=csrf_headers(calendar_client),
                json={"name": "Invalid", "sources": [source]},
            ).status_code
            == 404
        )
    seed_user(concurrent_engine, "other@example.com", password_hash)
    browser_login(calendar_client, "other@example.com")
    assert calendar_client.get(BASE).json()["items"] == []
    for method, suffix, payload in (
        ("GET", "", None),
        ("GET", "/events" + DATES, None),
        ("PATCH", "", {"expected_version": 1, "name": "Foreign"}),
        ("DELETE", "?expected_version=1", None),
    ):
        assert (
            calendar_client.request(
                method, path + suffix, headers=csrf_headers(calendar_client), json=payload
            ).status_code
            == 404
        )
    assert (
        calendar_client.post(
            BASE,
            headers=csrf_headers(calendar_client),
            json={
                "name": "Foreign filter",
                "sources": [{"source": "personal", "collection_ids": [collection["id"]]}],
            },
        ).status_code
        == 404
    )
    calendar_client.cookies.clear()
    for route in (BASE, path, path + "/events" + DATES):
        assert calendar_client.get(route).status_code == 401


def test_dynamic_membership_filters_sorting_and_deleted_filter(calendar_client: TestClient) -> None:
    first, second, third = (create_event(calendar_client) for _ in range(3))
    collections = [create_organization(calendar_client) for _ in range(2)]
    tags = [create_organization(calendar_client, "tags") for _ in range(2)]
    put(calendar_client, members(collections[0]), "personal", first["id"])
    put(calendar_client, members(collections[1]), "personal", second["id"])
    put(calendar_client, members(tags[1], "tags"), "personal", second["id"])
    view = create_view(
        calendar_client,
        sources=[
            {
                "source": "personal",
                "collection_ids": [row["id"] for row in collections],
                "tag_ids": [row["id"] for row in tags],
            }
        ],
        sort_order="desc",
    )
    path = f"{BASE}/{view['id']}"
    assert [
        row["source_event_id"]
        for row in calendar_client.get(path + "/events" + DATES).json()["events"]
    ] == [second["id"]]
    put(calendar_client, members(tags[0], "tags"), "personal", first["id"])
    response = calendar_client.get(path + "/events" + DATES).json()
    assert [row["source_event_id"] for row in response["events"]] == sorted(
        [first["id"], second["id"]], reverse=True
    )
    assert third["id"] not in str(response)
    changed = calendar_client.patch(
        f"/api/v1/calendar/personal-events/{second['id']}",
        headers=csrf_headers(calendar_client),
        json={"expected_version": 1, "title": "New title"},
    )
    assert changed.status_code == 200
    assert any(
        row["title"] == "New title"
        for row in calendar_client.get(path + "/events" + DATES).json()["events"]
    )
    assert (
        calendar_client.delete(
            f"/api/v1/workspace/tags/{tags[0]['id']}?expected_version=1",
            headers=csrf_headers(calendar_client),
        ).status_code
        == 204
    )
    assert calendar_client.get(path).json() == view
    assert calendar_client.get(path + "/events" + DATES).status_code == 409
    repaired = calendar_client.patch(
        path,
        headers=csrf_headers(calendar_client),
        json={
            "expected_version": 1,
            "sources": [{"source": "personal", "tag_ids": [tags[1]["id"]]}],
        },
    )
    assert repaired.status_code == 200
    assert len(calendar_client.get(path + "/events" + DATES).json()["events"]) == 1


def test_source_union_official_overrides_freshness_and_current_authorization(
    enrolled: TestClient, store: SqlAlchemyScheduleStore, concurrent_engine: Engine
) -> None:
    snapshot, now = schedule_fixture(), datetime.now(UTC)
    lesson = replace(expand_schedule(snapshot)[0], subgroup=1)
    token = store.claim(24066, "353501", now)
    assert token and store.apply(24066, token, snapshot, [lesson], now)
    personal = create_event(enrolled)
    create_event(enrolled)
    collection = create_organization(enrolled)
    put(enrolled, members(collection), "personal", personal["id"])
    view = create_view(
        enrolled,
        sources=[
            {"source": "official"},
            {"source": "personal", "collection_ids": [collection["id"]]},
        ],
    )
    path = f"{BASE}/{view['id']}"
    response = enrolled.get(path + "/events" + DATES).json()
    assert {row["source_event_id"] for row in response["events"]} == {
        personal["id"],
        str(lesson.id),
    }
    assert (
        enrolled.put(
            f"/api/v1/calendar/overrides/{lesson.id}",
            headers=csrf_headers(enrolled),
            json={"hidden": True, "starts_at": PAYLOAD["starts_at"], "ends_at": PAYLOAD["ends_at"]},
        ).status_code
        == 200
    )
    assert len(enrolled.get(path + "/events" + DATES).json()["events"]) == 1
    assert (
        enrolled.patch(
            path,
            headers=csrf_headers(enrolled),
            json={"expected_version": 1, "include_hidden": True},
        ).status_code
        == 200
    )
    events = enrolled.get(path + "/events" + DATES).json()["events"]
    official = next(row for row in events if row["source"] == "official")
    assert official["hidden"] and official["blocks_time"] and official["has_override"]
    assert official["starts_at"] == "2026-10-07T15:00:00Z"
    token = store.claim(24066, "353501", now + timedelta(hours=2))
    assert token
    store.fail(24066, token, "source_unavailable", now + timedelta(hours=2))
    response = enrolled.get(path + "/events" + DATES).json()
    assert response["source"]["status"] == "error" and "schedule_error" in response["warnings"]
    normal = enrolled.get("/api/v1/calendar/events" + DATES + "&include_hidden=true").json()
    assert len(normal["events"]) == 3 and normal["source"] == response["source"]
    official_collection = create_organization(enrolled)
    official_tag = create_organization(enrolled, "tags")
    put(enrolled, members(official_collection), "official", str(lesson.id))
    put(enrolled, members(official_tag, "tags"), "official", str(lesson.id))
    official_view = create_view(
        enrolled,
        sources=[
            {
                "source": "official",
                "collection_ids": [official_collection["id"]],
                "tag_ids": [official_tag["id"]],
            }
        ],
        include_hidden=True,
    )
    official_path = f"{BASE}/{official_view['id']}/events{DATES}"
    assert [row["source_event_id"] for row in enrolled.get(official_path).json()["events"]] == [
        str(lesson.id)
    ]
    with Session(concurrent_engine) as database, database.begin():
        database.execute(delete(AcademicProfileModel))
    response = enrolled.get(path + "/events" + DATES).json()
    assert [row["source_event_id"] for row in response["events"]] == [personal["id"]]
    assert "academic_profile_not_selected" in response["warnings"]
    assert enrolled.get(official_path).json()["events"] == []


def test_view_resolution_keeps_one_snapshot(
    calendar_client: TestClient, concurrent_engine: Engine
) -> None:
    event, collection = create_event(calendar_client), create_organization(calendar_client)
    put(calendar_client, members(collection), "personal", event["id"])
    view = create_view(
        calendar_client, sources=[{"source": "personal", "collection_ids": [collection["id"]]}]
    )
    original = SqlAlchemyMemberships.event_organizations

    def remove_membership(self, *args):
        with Session(concurrent_engine) as writer, writer.begin():
            writer.execute(delete(MembershipModel))
        return original(self, *args)

    path = f"{BASE}/{view['id']}/events{DATES}"
    with patch.object(SqlAlchemyMemberships, "event_organizations", remove_membership):
        assert len(calendar_client.get(path).json()["events"]) == 1
    assert calendar_client.get(path).json()["events"] == []


def test_failed_update_rolls_back_and_concurrent_edits_reject_stale(
    calendar_client: TestClient, concurrent_engine: Engine
) -> None:
    view = create_view(calendar_client)
    identifier = UUID(view["id"])
    path = f"{BASE}/{identifier}"
    original = SqlAlchemyCalendarViews.save

    def fail(self, value, expected_version):
        original(self, value, expected_version)
        raise SQLAlchemyError("private-view-sql")

    with patch.object(SqlAlchemyCalendarViews, "save", fail), capture_json() as output:
        response = calendar_client.patch(
            path,
            headers=csrf_headers(calendar_client),
            json={"expected_version": 1, "name": "Private update"},
        )
    assert response.status_code == 503 and "private" not in response.text
    assert "private-view-sql" not in output.getvalue()
    assert not any(row["event"] == "workspace.calendar_view_updated" for row in entries(output))
    assert calendar_client.get(path).json() == view
    with Session(concurrent_engine) as database:
        row = database.get(CalendarViewModel, identifier)
        assert row
        owner = row.user_id

    def edit(name: str) -> bool:
        try:
            with Session(concurrent_engine) as database, database.begin():
                service = CalendarViewService(
                    SqlAlchemyCalendarViews(database),
                    WorkspaceService(
                        SqlAlchemyOrganizations(database), SqlAlchemyUserAuthentication(database)
                    ),
                    SqlAlchemyMemberships(database),
                    Mock(),
                )
                service.update(owner, identifier, {"name": name}, 1)
            return True
        except WorkspaceConflict:
            return False

    with ThreadPoolExecutor(2) as workers:
        assert sorted(workers.map(edit, ["First", "Second"])) == [False, True]
    assert calendar_client.get(path).json()["version"] == 2
