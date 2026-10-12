from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_auth_http import browser_login, csrf_headers, seed_user
from test_calendar_http import browser_settings as browser_settings
from test_calendar_http import calendar_client as calendar_client
from test_calendar_http import concurrent_engine as concurrent_engine
from test_calendar_http import create_event
from test_calendar_http import enrolled as enrolled
from test_calendar_http import live_client as live_client
from test_calendar_http import password_hash as password_hash
from test_calendar_http import settings as settings
from test_calendar_http import store as store
from test_logging import capture_json, entries
from test_notes_http import BASE as NOTES
from test_notes_http import change, create_page, lifecycle
from test_schedule_expansion import schedule_fixture

from app.modules.academics.infrastructure.orm import AcademicProfileModel
from app.modules.notes.infrastructure.orm import PageModel
from app.modules.relations.domain.links import CalendarPageLink
from app.modules.relations.infrastructure.orm import CalendarPageLinkModel
from app.modules.relations.infrastructure.repository import SqlAlchemyCalendarPageLinks
from app.modules.schedule.application.expansion import expand_schedule
from app.modules.schedule.infrastructure.storage import SqlAlchemyScheduleStore

BASE = "/api/v1/relations"


def event_path(source: str, identifier: str) -> str:
    return f"{BASE}/calendar-events/{source}/{identifier}/pages"


def backlinks(client: TestClient, page: dict) -> dict:
    response = client.get(f"{BASE}/pages/{page['id']}/calendar-events")
    assert response.status_code == 200, response.text
    return response.json()


def test_multiple_events_share_page_without_propagating_edits(calendar_client: TestClient) -> None:
    page = create_page(calendar_client, content="private-page-content")
    first, second = create_event(calendar_client), create_event(calendar_client)
    path = event_path("personal", first["id"])
    with capture_json() as output:
        link = calendar_client.put(f"{path}/{page['id']}", headers=csrf_headers(calendar_client))
        assert link.status_code == 200
        duplicate = calendar_client.put(
            f"{path}/{page['id']}", headers=csrf_headers(calendar_client)
        )
        assert duplicate.json() == link.json()
        assert (
            calendar_client.put(
                f"{event_path('personal', second['id'])}/{page['id']}",
                headers=csrf_headers(calendar_client),
            ).status_code
            == 200
        )
        assert len(backlinks(calendar_client, page)["items"]) == 2
        assert len(calendar_client.get(path).json()["items"]) == 1
        assert calendar_client.get(path + "?offset=1").json()["items"] == []
        assert "user_id" not in link.json()["link"] and "content" not in link.json()["page"]
        changed = change(calendar_client, page, content="Changed").json()
        assert (
            calendar_client.get(f"/api/v1/calendar/personal-events/{first['id']}").json() == first
        )
        assert (
            calendar_client.patch(
                f"/api/v1/calendar/personal-events/{first['id']}",
                headers=csrf_headers(calendar_client),
                json={"expected_version": 1, "title": "New title"},
            ).status_code
            == 200
        )
        assert calendar_client.get(f"{NOTES}/{page['id']}").json() == changed
        reference = backlinks(calendar_client, page)["items"][0]["event"]
        assert reference["title"] == "New title" and reference["source_status"] == "active"
        assert (
            calendar_client.delete(
                f"{path}/{page['id']}", headers=csrf_headers(calendar_client)
            ).status_code
            == 204
        )
        assert len(backlinks(calendar_client, page)["items"]) == 1
        assert calendar_client.get(f"{NOTES}/{page['id']}").json() == changed
        assert (
            calendar_client.get(f"/api/v1/calendar/personal-events/{first['id']}").status_code
            == 200
        )
    assert page["id"] not in output.getvalue() and "private-page-content" not in output.getvalue()
    assert any(row["event"] == "relations.page_linked" for row in entries(output))
    assert calendar_client.get(path).headers["cache-control"] == "no-store"


def test_create_from_event_and_trash_keep_links(calendar_client: TestClient) -> None:
    group = create_page(calendar_client)
    event = create_event(calendar_client)
    path = event_path("personal", event["id"])
    response = calendar_client.post(
        path,
        headers=csrf_headers(calendar_client),
        json={"title": "Chest", "content": "Press", "parent_id": group["id"]},
    )
    assert response.status_code == 201
    page = calendar_client.get(f"{NOTES}/{response.json()['page']['id']}").json()
    assert page["content"] == "Press" and page["parent_id"] == group["id"]
    trashed = lifecycle(calendar_client, group, "trash")
    assert trashed.status_code == 200
    stored = calendar_client.get(path).json()["items"][0]
    assert stored["page"]["trashed_at"] is not None
    assert len(backlinks(calendar_client, page)["items"]) == 1
    assert (
        calendar_client.put(
            f"{path}/{page['id']}", headers=csrf_headers(calendar_client)
        ).status_code
        == 409
    )
    assert lifecycle(calendar_client, trashed.json(), "restore").status_code == 200
    assert calendar_client.get(path).json()["items"][0]["page"]["trashed_at"] is None
    assert (
        calendar_client.delete(
            f"/api/v1/calendar/personal-events/{event['id']}", headers=csrf_headers(calendar_client)
        ).status_code
        == 204
    )
    assert backlinks(calendar_client, page)["items"] == []
    assert calendar_client.get(f"{NOTES}/{page['id']}").json()["content"] == "Press"


def test_official_links_survive_refresh_withdrawal_and_profile_changes(
    enrolled: TestClient,
    store: SqlAlchemyScheduleStore,
    concurrent_engine: Engine,
) -> None:
    snapshot = schedule_fixture()
    lesson = replace(expand_schedule(snapshot)[0], subgroup=1)
    other = replace(lesson, id=uuid4(), subgroup=2)
    now = datetime.now(UTC)
    token = store.claim(24066, "353501", now)
    assert token and store.apply(24066, token, snapshot, [lesson, other], now)
    page = create_page(enrolled)
    path = event_path("official", str(lesson.id))
    assert enrolled.put(f"{path}/{page['id']}", headers=csrf_headers(enrolled)).status_code == 200
    assert (
        enrolled.put(
            f"{event_path('official', str(other.id))}/{page['id']}", headers=csrf_headers(enrolled)
        ).status_code
        == 404
    )
    assert (
        enrolled.put(
            f"/api/v1/calendar/overrides/{lesson.id}",
            headers=csrf_headers(enrolled),
            json={
                "title": "My lecture",
                "skipped": True,
                "starts_at": "2026-09-14T15:00:00Z",
                "ends_at": "2026-09-14T16:00:00Z",
            },
        ).status_code
        == 200
    )
    reference = backlinks(enrolled, page)["items"][0]["event"]
    assert reference["title"] == "My lecture" and reference["skipped"]
    assert reference["starts_at"] == "2026-09-14T15:00:00Z"
    now += timedelta(hours=2)
    token = store.claim(24066, "353501", now)
    changed = replace(lesson, id=uuid4(), rooms=("new",))
    assert token and store.apply(24066, token, snapshot, [changed], now)
    assert enrolled.get(path).json()["items"][0]["link"]["event_id"] == str(lesson.id)
    with Session(concurrent_engine) as database, database.begin():
        database.query(AcademicProfileModel).one().subgroup = 2
    assert backlinks(enrolled, page)["items"][0]["event"]["source_status"] == "outside_profile"
    assert enrolled.put(f"{path}/{page['id']}", headers=csrf_headers(enrolled)).status_code == 404
    assert enrolled.get(path + "?offset=1").json()["items"] == []
    now += timedelta(hours=2)
    token = store.claim(24066, "353501", now)
    assert token and store.apply(24066, token, None, [], now)
    assert backlinks(enrolled, page)["items"][0]["event"]["source_status"] == "inactive_source"
    assert enrolled.get(path).status_code == 200
    new_page = create_page(enrolled)
    with Session(concurrent_engine) as database, database.begin():
        database.query(AcademicProfileModel).one().subgroup = 1
    assert (
        enrolled.put(f"{path}/{new_page['id']}", headers=csrf_headers(enrolled)).status_code == 409
    )
    assert (
        enrolled.delete(f"{path}/{page['id']}", headers=csrf_headers(enrolled)).status_code == 204
    )
    assert backlinks(enrolled, page)["items"] == []


def test_sessions_csrf_and_both_endpoint_owners(
    calendar_client: TestClient, concurrent_engine: Engine, password_hash: str
) -> None:
    page, event = create_page(calendar_client), create_event(calendar_client)
    path = event_path("personal", event["id"])
    assert (
        calendar_client.put(
            f"{path}/{page['id']}", headers=csrf_headers(calendar_client)
        ).status_code
        == 200
    )
    for method, route, payload in (
        ("PUT", f"{path}/{page['id']}", None),
        ("DELETE", f"{path}/{page['id']}", None),
        ("POST", path, {"title": "T"}),
    ):
        assert calendar_client.request(method, route, json=payload).status_code == 403
    seed_user(concurrent_engine, "other@example.com", password_hash)
    browser_login(calendar_client, "other@example.com")
    own_page, own_event = create_page(calendar_client), create_event(calendar_client)
    for route in (
        f"{path}/{own_page['id']}",
        f"{event_path('personal', own_event['id'])}/{page['id']}",
    ):
        assert calendar_client.put(route, headers=csrf_headers(calendar_client)).status_code == 404
    assert calendar_client.get(path).status_code == 404
    assert calendar_client.get(f"{BASE}/pages/{page['id']}/calendar-events").status_code == 404
    assert (
        calendar_client.delete(
            f"{path}/{page['id']}", headers=csrf_headers(calendar_client)
        ).status_code
        == 404
    )
    assert (
        calendar_client.post(
            path, headers=csrf_headers(calendar_client), json={"title": "T"}
        ).status_code
        == 404
    )
    assert len(calendar_client.get(NOTES).json()["items"]) == 1
    assert backlinks(calendar_client, own_page)["items"] == []
    calendar_client.cookies.clear()
    assert calendar_client.get(path).status_code == 401
    assert calendar_client.get(f"{BASE}/pages/{page['id']}/calendar-events").status_code == 401


@pytest.mark.parametrize("failure", ["missing_event", "failed_insert"])
def test_atomic_create_rolls_back(calendar_client: TestClient, failure: str) -> None:
    event = create_event(calendar_client)
    path = event_path("personal", event["id"] if failure == "failed_insert" else str(uuid4()))
    original = SqlAlchemyCalendarPageLinks.put

    def fail(self, link):
        original(self, link)
        raise SQLAlchemyError("private-link-sql")

    if failure == "failed_insert":
        with patch.object(SqlAlchemyCalendarPageLinks, "put", fail), capture_json() as output:
            response = calendar_client.post(
                path, headers=csrf_headers(calendar_client), json={"title": "T"}
            )
        assert response.status_code == 503 and "private" not in output.getvalue()
        assert not any(row["event"] == "relations.linked_page_created" for row in entries(output))
    else:
        response = calendar_client.post(
            path, headers=csrf_headers(calendar_client), json={"title": "T"}
        )
        assert response.status_code == 404
    application = cast(FastAPI, calendar_client.app)
    with application.state.session_factory() as database:
        assert database.scalar(select(PageModel)) is None
        assert database.scalar(select(CalendarPageLinkModel)) is None


def test_duplicate_links_are_safe_under_concurrent_inserts(
    calendar_client: TestClient, concurrent_engine: Engine
) -> None:
    page, event = create_page(calendar_client), create_event(calendar_client)
    with Session(concurrent_engine) as database:
        stored = database.get(PageModel, UUID(page["id"]))
        assert stored
        owner = stored.user_id

    def put() -> UUID:
        with Session(concurrent_engine) as database, database.begin():
            link = CalendarPageLink(
                uuid4(), owner, UUID(page["id"]), "personal", UUID(event["id"]), datetime.now(UTC)
            )
            return SqlAlchemyCalendarPageLinks(database).put(link).id

    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(put), pool.submit(put)]
        assert futures[0].result() == futures[1].result()
    assert len(backlinks(calendar_client, page)["items"]) == 1


@pytest.mark.parametrize("query", ["limit=0", "limit=201", "offset=-1", "offset=2147483648"])
def test_relation_pagination_is_bounded(calendar_client: TestClient, query: str) -> None:
    page, event = create_page(calendar_client), create_event(calendar_client)
    for route in (
        event_path("personal", event["id"]),
        f"{BASE}/pages/{page['id']}/calendar-events",
    ):
        assert calendar_client.get(f"{route}?{query}").status_code == 422
