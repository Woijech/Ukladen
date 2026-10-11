from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_auth_http import browser_login, csrf_headers, seed_user
from test_auth_http import browser_settings as browser_settings
from test_auth_http import live_client as live_client
from test_auth_login import password_hash as password_hash
from test_auth_sessions import concurrent_engine as concurrent_engine
from test_auth_sessions import settings as settings
from test_logging import capture_json, entries
from test_schedule_events_http import enrolled as enrolled
from test_schedule_expansion import schedule_fixture
from test_schedule_storage import store as store

from app.modules.academics.infrastructure.orm import AcademicProfileModel
from app.modules.calendar.application.service import CalendarService
from app.modules.calendar.domain.events import CalendarConflict
from app.modules.calendar.infrastructure.orm import PersonalCalendarEventModel
from app.modules.calendar.infrastructure.repository import SqlAlchemyCalendarRepository
from app.modules.schedule.application.expansion import expand_schedule
from app.modules.schedule.infrastructure.orm import OfficialScheduleEventModel
from app.modules.schedule.infrastructure.storage import SqlAlchemyScheduleStore
from app.modules.users.infrastructure.repository import SqlAlchemyProfileRepository

BASE = "/api/v1/calendar"
PAYLOAD = {
    "title": " Study ",
    "description": "private-content",
    "starts_at": "2026-10-07T18:00:00+03:00",
    "ends_at": "2026-10-07T19:00:00+03:00",
    "location": "private-location",
    "blocks_time": True,
}


@pytest.fixture
def calendar_client(
    live_client: TestClient, concurrent_engine: Engine, password_hash: str
) -> Iterator[TestClient]:
    seed_user(concurrent_engine, "student@example.com", password_hash)
    browser_login(live_client)
    yield live_client


def create_event(client: TestClient) -> dict:
    response = client.post(f"{BASE}/personal-events", headers=csrf_headers(client), json=PAYLOAD)
    assert response.status_code == 201, response.text
    return response.json()


def test_personal_crud_without_academic_profile_and_private_logs(
    calendar_client: TestClient,
) -> None:
    with capture_json() as output:
        created = create_event(calendar_client)
        identifier = created["id"]
        assert created["title"] == "Study" and created["version"] == 1
        assert "user_id" not in created and created["starts_at"] == "2026-10-07T15:00:00Z"
        read = calendar_client.get(f"{BASE}/personal-events/{identifier}")
        assert read.status_code == 200 and read.json() == created
        resolved = calendar_client.get(f"{BASE}/events?date_from=2026-10-07&date_to=2026-10-07")
        assert resolved.status_code == 200
        assert resolved.json()["source"] is None
        assert resolved.json()["warnings"] == ["academic_profile_not_selected"]
        assert resolved.json()["events"][0]["source_event_id"] == identifier
        changed = calendar_client.patch(
            f"{BASE}/personal-events/{identifier}",
            headers=csrf_headers(calendar_client),
            json={"expected_version": 1, "description": None, "blocks_time": False},
        )
        assert changed.status_code == 200 and changed.json()["version"] == 2
        assert changed.json()["description"] is None and not changed.json()["blocks_time"]
        assert changed.json()["location"] == created["location"]
        stale = calendar_client.patch(
            f"{BASE}/personal-events/{identifier}",
            headers=csrf_headers(calendar_client),
            json={"expected_version": 1, "title": "Overwrite"},
        )
        assert stale.status_code == 409
        invalid = calendar_client.patch(
            f"{BASE}/personal-events/{identifier}",
            headers=csrf_headers(calendar_client),
            json={"expected_version": 2, "starts_at": "2026-10-07T20:00:00+03:00"},
        )
        assert invalid.status_code == 422
        assert calendar_client.get(f"{BASE}/personal-events/{identifier}").json() == changed.json()
        deleted = calendar_client.delete(
            f"{BASE}/personal-events/{identifier}", headers=csrf_headers(calendar_client)
        )
        assert deleted.status_code == 204 and deleted.content == b""
        assert calendar_client.get(f"{BASE}/personal-events/{identifier}").status_code == 404
    assert (
        "private-content" not in output.getvalue() and "private-location" not in output.getvalue()
    )
    assert identifier not in output.getvalue()
    records = entries(output)
    for event in (
        "calendar.personal_event_created",
        "calendar.personal_event_updated",
        "calendar.personal_event_deleted",
        "calendar.resolved",
        "calendar.operation_rejected",
    ):
        record = next(item for item in records if item["event"] == event)
        assert len(record["request_id"]) == 32
    assert resolved.headers["cache-control"] == "no-store"


def test_sessions_csrf_and_ownership(
    calendar_client: TestClient, concurrent_engine: Engine, password_hash: str
) -> None:
    created = create_event(calendar_client)
    path = f"{BASE}/personal-events/{created['id']}"
    for method, route, payload in (
        ("POST", f"{BASE}/personal-events", PAYLOAD),
        ("PATCH", path, {"expected_version": 1, "title": "Other"}),
        ("DELETE", path, None),
        ("PUT", f"{BASE}/overrides/{uuid4()}", {"skipped": True}),
        ("DELETE", f"{BASE}/overrides/{uuid4()}", None),
    ):
        assert calendar_client.request(method, route, json=payload).status_code == 403
    seed_user(concurrent_engine, "other@example.com", password_hash)
    browser_login(calendar_client, "other@example.com")
    headers = csrf_headers(calendar_client)
    for method, payload in (
        ("GET", None),
        ("PATCH", {"expected_version": 1, "title": "Other"}),
        ("DELETE", None),
    ):
        assert (
            calendar_client.request(method, path, headers=headers, json=payload).status_code == 404
        )
    assert (
        calendar_client.get(f"{BASE}/events?date_from=2026-10-07&date_to=2026-10-07").json()[
            "events"
        ]
        == []
    )
    calendar_client.cookies.clear()
    for route in (
        path,
        f"{BASE}/events?date_from=2026-10-07&date_to=2026-10-07",
        f"{BASE}/overrides",
    ):
        assert calendar_client.get(route).status_code == 401


@pytest.mark.parametrize(
    "changes",
    [
        {"title": " "},
        {"user_id": "protected"},
        {"blocks_time": "true"},
        {"starts_at": "2026-10-07T18:00:00"},
        {"ends_at": "2026-10-07T18:00:00+03:00"},
        {"location": "a" * 501},
    ],
)
def test_create_validation(calendar_client: TestClient, changes: dict) -> None:
    response = calendar_client.post(
        f"{BASE}/personal-events", headers=csrf_headers(calendar_client), json=PAYLOAD | changes
    )
    assert response.status_code == 422
    assert (
        calendar_client.get(f"{BASE}/events?date_from=2026-10-07&date_to=2026-10-07").json()[
            "events"
        ]
        == []
    )


def test_calendar_dates_follow_profile_timezone_and_overlap(calendar_client: TestClient) -> None:
    assert (
        calendar_client.patch(
            "/api/v1/users/me",
            headers=csrf_headers(calendar_client),
            json={"timezone": "Europe/Minsk"},
        ).status_code
        == 200
    )
    for start, end, title in (
        ("2026-10-06T20:30:00Z", "2026-10-06T21:30:00Z", "Cross-midnight"),
        ("2026-10-06T20:00:00Z", "2026-10-06T21:00:00Z", "Touches start"),
        ("2026-10-07T21:00:00Z", "2026-10-07T22:00:00Z", "Touches end"),
    ):
        response = calendar_client.post(
            f"{BASE}/personal-events",
            headers=csrf_headers(calendar_client),
            json=PAYLOAD | {"title": title, "starts_at": start, "ends_at": end},
        )
        assert response.status_code == 201
    response = calendar_client.get(f"{BASE}/events?date_from=2026-10-07&date_to=2026-10-07")
    assert response.json()["timezone"] == "Europe/Minsk"
    assert [item["title"] for item in response.json()["events"]] == ["Cross-midnight"]
    for query in (
        "date_from=0001-01-01&date_to=0001-01-01",
        "date_from=2026-01-01&date_to=2027-01-02",
        "date_from=2026-10-08&date_to=2026-10-07",
        "date_from=2026-10-07",
        "date_from=invalid&date_to=2026-10-07",
    ):
        assert calendar_client.get(f"{BASE}/events?{query}").status_code == 422


@pytest.mark.parametrize(
    "query",
    [
        "date_from=0&date_to=0",
        "date_from=2026-10-07&date_to=1791331200",
        "date_from=2026-10-07T00:00:00Z&date_to=2026-10-07",
        "date_from=2026-10-07&date_to=2026-10-07T00:00:00Z",
    ],
)
def test_calendar_rejects_non_date_query_parameters(
    calendar_client: TestClient, query: str
) -> None:
    response = calendar_client.get(f"{BASE}/events?{query}")
    assert response.status_code == 422


def test_overrides_moved_dates_subgroups_and_restore(
    enrolled: TestClient, store: SqlAlchemyScheduleStore
) -> None:
    snapshot = schedule_fixture()
    original = expand_schedule(snapshot)[0]
    lesson = replace(original, subgroup=1)
    other = replace(original, id=uuid4(), subgroup=2)
    announcement = replace(original, id=uuid4(), kind="announcement", subgroup=0)
    now = datetime.now(UTC)
    token = store.claim(24066, "353501", now)
    assert token and store.apply(24066, token, snapshot, [lesson, other, announcement], now)
    path = f"{BASE}/overrides/{lesson.id}"
    headers = csrf_headers(enrolled)
    before = enrolled.get(f"{BASE}/events?date_from=2026-09-01&date_to=2026-09-30").json()
    assert len(before["events"]) == 2 and before["source"]["status"] == "ready"
    assert not next(item for item in before["events"] if item["kind"] == "announcement")[
        "blocks_time"
    ]
    assert (
        enrolled.put(
            f"{BASE}/overrides/{other.id}", headers=headers, json={"skipped": True}
        ).status_code
        == 404
    )
    hidden = enrolled.put(path, headers=headers, json={"hidden": True})
    assert hidden.status_code == 200 and hidden.json()["version"] == 1
    assert (
        len(enrolled.get(f"{BASE}/events?date_from=2026-09-01&date_to=2026-09-30").json()["events"])
        == 1
    )
    visible = enrolled.get(
        f"{BASE}/events?date_from=2026-09-01&date_to=2026-09-30&include_hidden=true"
    ).json()["events"]
    assert next(item for item in visible if item["source_event_id"] == str(lesson.id))[
        "blocks_time"
    ]
    moved = enrolled.put(
        path,
        headers=headers,
        json={
            "expected_version": 1,
            "skipped": True,
            "title": "My OOP",
            "starts_at": "2026-10-07T10:00:00Z",
            "ends_at": "2026-10-07T11:00:00Z",
        },
    )
    assert moved.status_code == 200 and not moved.json()["hidden"]
    result = enrolled.get(f"{BASE}/events?date_from=2026-10-07&date_to=2026-10-07").json()["events"]
    assert len(result) == 1 and result[0]["title"] == "My OOP" and not result[0]["blocks_time"]
    assert (
        len(enrolled.get(f"{BASE}/events?date_from=2026-09-01&date_to=2026-09-30").json()["events"])
        == 1
    )
    assert store.event(lesson.id) == lesson
    assert (
        enrolled.put(
            path, headers=headers, json={"expected_version": 1, "hidden": True}
        ).status_code
        == 409
    )
    assert (
        enrolled.put(
            path, headers=headers, json={"expected_version": 2, "starts_at": "2026-10-07T10:00:00Z"}
        ).status_code
        == 422
    )
    assert enrolled.delete(path, headers=headers).status_code == 204
    assert (
        enrolled.get(f"{BASE}/events?date_from=2026-10-07&date_to=2026-10-07").json()["events"]
        == []
    )
    assert enrolled.get(f"{BASE}/overrides").json()["items"] == []


def test_overrides_survive_source_refresh_withdrawal_and_profile_change(
    enrolled: TestClient, store: SqlAlchemyScheduleStore, concurrent_engine: Engine
) -> None:
    snapshot = schedule_fixture()
    lesson = replace(expand_schedule(snapshot)[0], subgroup=1)
    now = datetime.now(UTC)
    token = store.claim(24066, "353501", now)
    assert token and store.apply(24066, token, snapshot, [lesson], now)
    path, headers = f"{BASE}/overrides/{lesson.id}", csrf_headers(enrolled)
    assert enrolled.put(path, headers=headers, json={"skipped": True}).status_code == 200
    now += timedelta(hours=2)
    token = store.claim(24066, "353501", now)
    changed = replace(
        lesson,
        id=uuid4(),
        rooms=("new room",),
        starts_at=lesson.starts_at + timedelta(hours=1),
        ends_at=lesson.ends_at + timedelta(hours=1),
    )
    assert token and store.apply(24066, token, snapshot, [changed], now)
    result = enrolled.get(f"{BASE}/events?date_from=2026-09-01&date_to=2026-09-30").json()[
        "events"
    ][0]
    assert result["source_event_id"] == str(lesson.id) and result["location"] == "new room"
    assert result["skipped"] and not result["blocks_time"]
    now += timedelta(hours=2)
    token = store.claim(24066, "353501", now)
    assert token
    store.fail(24066, token, "source_unavailable", now)
    degraded = enrolled.get(f"{BASE}/events?date_from=2026-09-01&date_to=2026-09-30").json()
    assert degraded["source"]["status"] == "error" and degraded["events"][0]["skipped"]
    with Session(concurrent_engine) as database, database.begin():
        database.query(AcademicProfileModel).one().subgroup = 2
    assert (
        enrolled.get(f"{BASE}/overrides").json()["items"][0]["source_status"] == "outside_profile"
    )
    now += timedelta(hours=2)
    token = store.claim(24066, "353501", now)
    assert token and store.apply(24066, token, None, [], now)
    assert (
        enrolled.get(f"{BASE}/overrides").json()["items"][0]["source_status"] == "inactive_source"
    )
    assert (
        enrolled.get(f"{BASE}/events?date_from=2026-09-01&date_to=2026-09-30").json()["events"]
        == []
    )
    with Session(concurrent_engine) as database, database.begin():
        database.query(AcademicProfileModel).one().subgroup = 1
    assert (
        enrolled.put(
            path, headers=headers, json={"expected_version": 1, "hidden": True}
        ).status_code
        == 409
    )
    with Session(concurrent_engine) as database, database.begin():
        database.delete(database.query(AcademicProfileModel).one())
    assert enrolled.delete(path, headers=headers).status_code == 204


@pytest.mark.parametrize("failure", ["write", "commit"])
def test_database_failure_rolls_back_without_success_log(
    calendar_client: TestClient, concurrent_engine: Engine, failure: str
) -> None:
    application = cast(FastAPI, calendar_client.app)
    headers = csrf_headers(calendar_client)
    original = SqlAlchemyCalendarRepository.create_personal

    def fail_write(self, event):
        original(self, event)
        if failure == "commit":
            self.session.get_transaction().commit = lambda: (_ for _ in ()).throw(
                SQLAlchemyError("private-commit")
            )
        else:
            raise SQLAlchemyError("private-sql-payload")

    with (
        patch.object(SqlAlchemyCalendarRepository, "create_personal", fail_write),
        capture_json() as output,
    ):
        response = calendar_client.post(f"{BASE}/personal-events", headers=headers, json=PAYLOAD)
    assert response.status_code == 503 and "private" not in response.text
    assert not any(item["event"] == "calendar.personal_event_created" for item in entries(output))
    assert "private" not in output.getvalue()
    with application.state.session_factory() as database:
        assert database.scalar(select(PersonalCalendarEventModel)) is None
    assert create_event(calendar_client)["version"] == 1


def test_concurrent_edits_reject_stale_version(
    calendar_client: TestClient, concurrent_engine: Engine
) -> None:
    created = create_event(calendar_client)
    event_id = UUID(created["id"])
    with Session(concurrent_engine) as database:
        row = database.get(PersonalCalendarEventModel, event_id)
        assert row is not None
        user_id = row.user_id

    def edit(title: str) -> bool:
        try:
            with Session(concurrent_engine) as database, database.begin():
                service = CalendarService(
                    SqlAlchemyCalendarRepository(database),
                    SqlAlchemyProfileRepository(database),
                    Mock(),
                    Mock(),
                )
                service.update_personal_event(user_id, event_id, {"title": title}, 1)
            return True
        except CalendarConflict:
            return False

    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(workers.map(edit, ["First", "Second"])) == [False, True]
    saved = calendar_client.get(f"{BASE}/personal-events/{event_id}").json()
    assert saved["version"] == 2 and saved["title"] in ("First", "Second")
    assert saved["description"] == created["description"]


def test_resolution_uses_one_snapshot_across_modules(
    enrolled: TestClient, store: SqlAlchemyScheduleStore, concurrent_engine: Engine
) -> None:
    snapshot = schedule_fixture()
    lesson = replace(expand_schedule(snapshot)[0], subgroup=1)
    now = datetime.now(UTC)
    token = store.claim(24066, "353501", now)
    assert token and store.apply(24066, token, snapshot, [lesson], now)
    personal = create_event(enrolled)
    original = SqlAlchemyCalendarRepository.moved_overrides

    def concurrent_change(self, user_id, starts_at, ends_at):
        with Session(concurrent_engine) as writer, writer.begin():
            event = writer.get(OfficialScheduleEventModel, lesson.id)
            assert event is not None
            event.active = False
            own = writer.get(PersonalCalendarEventModel, UUID(personal["id"]))
            assert own is not None
            own.title = "Changed after snapshot"
        return original(self, user_id, starts_at, ends_at)

    path = f"{BASE}/events?date_from=2026-09-01&date_to=2026-10-31"
    with patch.object(SqlAlchemyCalendarRepository, "moved_overrides", concurrent_change):
        result = enrolled.get(path)
    assert result.status_code == 200
    assert len(result.json()["events"]) == 2
    assert (
        next(item for item in result.json()["events"] if item["source"] == "personal")["title"]
        == "Study"
    )
    after = enrolled.get(path).json()["events"]
    assert len(after) == 1 and after[0]["title"] == "Changed after snapshot"
