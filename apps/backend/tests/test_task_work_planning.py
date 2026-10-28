from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_auth_http import csrf_headers
from test_calendar_http import browser_settings as browser_settings
from test_calendar_http import calendar_client as calendar_client
from test_calendar_http import concurrent_engine as concurrent_engine
from test_calendar_http import live_client as live_client
from test_calendar_http import password_hash as password_hash
from test_calendar_http import settings as settings
from test_tasks_http import BASE, create_task

from app.modules.tasks.domain.planning import WeeklyWindow, WorkPreferences
from app.modules.tasks.domain.tasks import InvalidTaskInput
from app.modules.tasks.infrastructure.planning import WorkSessionModel

PLANNING = BASE + "/planning"
START = datetime(2030, 10, 28, 9, tzinfo=UTC)


def session_payload(client, task, start=START, end=START + timedelta(minutes=45), **extra):
    values = {
        "task_id": task["id"],
        "starts_at": start.isoformat(),
        "ends_at": end.isoformat(),
    } | extra
    checked = client.post(PLANNING + "/sessions/check", headers=csrf_headers(client), json=values)
    assert checked.status_code == 200, checked.text
    return values | {"snapshot": checked.json()["snapshot"]}


def test_weekly_windows_validate_overlap_and_dst_boundaries():
    prefs = WorkPreferences(windows=(WeeklyWindow(0, 540, 1020),))
    windows = prefs.expand(START, START + timedelta(days=7), "Europe/Minsk")
    assert windows[0].starts_at == START and windows[0].ends_at == START + timedelta(hours=5)
    for args in ((True, 0, 1), (7, 0, 1), (0, 60, 60), (0, 0, 1441)):
        with pytest.raises(InvalidTaskInput):
            WeeklyWindow(*args)
    with pytest.raises(InvalidTaskInput):
        WorkPreferences(windows=(WeeklyWindow(0, 0, 90), WeeklyWindow(0, 60, 100)))
    ambiguous = WorkPreferences(windows=(WeeklyWindow(6, 150, 210),))
    for start in (datetime(2026, 10, 25, tzinfo=UTC), datetime(2026, 3, 29, tzinfo=UTC)):
        with pytest.raises(InvalidTaskInput):
            ambiguous.expand(start, start + timedelta(days=1), "Europe/Berlin")


def test_preferences_are_versioned_and_remaining_is_explicit(calendar_client: TestClient):
    client = calendar_client
    assert client.get(PLANNING + "/preferences").json() == {
        "version": 0,
        "windows": [],
        "session_minutes": 45,
        "break_minutes": 15,
    }
    values = {
        "expected_version": 0,
        "windows": [{"weekday": 0, "start_minute": 540, "end_minute": 1020}],
    }
    assert client.put(PLANNING + "/preferences", json=values).status_code == 403
    saved = client.put(PLANNING + "/preferences", headers=csrf_headers(client), json=values)
    assert saved.status_code == 200, saved.text
    assert saved.json()["version"] == 1
    assert (
        client.put(PLANNING + "/preferences", headers=csrf_headers(client), json=values).status_code
        == 409
    )
    task = create_task(client, estimated_minutes=90)
    assert task["remaining_minutes"] is None
    changed = client.patch(
        BASE + "/" + task["id"],
        headers=csrf_headers(client),
        json={"expected_version": 1, "remaining_minutes": 30},
    )
    assert changed.status_code == 200 and changed.json()["remaining_minutes"] == 30
    for invalid in (-1, True, "20", 525601):
        assert (
            client.patch(
                BASE + "/" + task["id"],
                headers=csrf_headers(client),
                json={"expected_version": 2, "remaining_minutes": invalid},
            ).status_code
            == 422
        )


def test_manual_session_busy_pin_move_cancel_and_stale_snapshot(calendar_client: TestClient):
    client = calendar_client
    task = create_task(client, remaining_minutes=90)
    payload = session_payload(client, task)
    saved = client.post(PLANNING + "/sessions", headers=csrf_headers(client), json=payload)
    assert saved.status_code == 201, saved.text
    item = saved.json()
    availability = client.post(
        "/api/v1/calendar/availability",
        headers=csrf_headers(client),
        json={
            "starts_at": START.isoformat(),
            "ends_at": (START + timedelta(hours=2)).isoformat(),
            "windows": [],
        },
    ).json()
    assert availability["events"][0]["source"] == "task_session" and "user_id" not in item
    assert (
        client.post(PLANNING + "/sessions", headers=csrf_headers(client), json=payload).status_code
        == 409
    )
    path = PLANNING + "/sessions/" + item["id"]
    pinned = client.patch(
        path, headers=csrf_headers(client), json={"expected_version": 1, "pinned": True}
    )
    assert pinned.status_code == 200 and pinned.json()["pinned"]
    moved = session_payload(
        client, task, START + timedelta(hours=1), START + timedelta(hours=2), session_id=item["id"]
    )
    updated = client.post(
        PLANNING + "/sessions",
        headers=csrf_headers(client),
        json=moved | {"expected_version": 2, "pinned": True},
    )
    assert updated.status_code == 201 and updated.json()["version"] == 3
    cancelled = client.patch(
        path, headers=csrf_headers(client), json={"expected_version": 3, "cancel": True}
    )
    assert cancelled.status_code == 200 and cancelled.json()["cancelled"]
    assert client.get(BASE + "/" + task["id"]).json()["remaining_minutes"] == 90
    assert (
        client.patch(
            path, headers=csrf_headers(client), json={"expected_version": 4, "pinned": False}
        ).status_code
        == 409
    )
    assert (
        client.patch(
            PLANNING + "/sessions/" + str(uuid4()),
            headers=csrf_headers(client),
            json={"expected_version": 1, "cancel": True},
        ).status_code
        == 404
    )


def test_manual_conflicts_require_exact_ack_and_task_lifecycle_cancels_future(
    calendar_client: TestClient, concurrent_engine: Engine
):
    client = calendar_client
    task = create_task(client, remaining_minutes=90)
    first = client.post(
        PLANNING + "/sessions", headers=csrf_headers(client), json=session_payload(client, task)
    ).json()
    conflicting = session_payload(client, task)
    assert (
        client.post(
            PLANNING + "/sessions", headers=csrf_headers(client), json=conflicting
        ).status_code
        == 409
    )
    accepted = client.post(
        PLANNING + "/sessions",
        headers=csrf_headers(client),
        json=conflicting | {"acknowledge_conflicts": True},
    )
    assert accepted.status_code == 201, accepted.text
    with Session(concurrent_engine) as db, db.begin():
        db.execute(
            update(WorkSessionModel)
            .where(WorkSessionModel.id == UUID(first["id"]))
            .values(
                starts_at=datetime(2020, 1, 1, tzinfo=UTC),
                ends_at=datetime(2020, 1, 1, 1, tzinfo=UTC),
            )
        )
    result = client.patch(
        BASE + "/" + task["id"],
        headers=csrf_headers(client),
        json={"expected_version": 1, "status": "done"},
    )
    assert result.status_code == 200
    with Session(concurrent_engine) as db:
        rows = list(db.scalars(select(WorkSessionModel).order_by(WorkSessionModel.starts_at)))
        assert not rows[0].cancelled and rows[1].cancelled
    assert result.json()["remaining_minutes"] == 90


def test_competing_manual_sessions_serialize(calendar_client: TestClient):
    client = calendar_client
    task = create_task(client)
    payload = session_payload(client, task)
    headers = csrf_headers(client)

    def create(_):
        return client.post(PLANNING + "/sessions", headers=headers, json=payload).status_code

    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(workers.map(create, range(2))) == [201, 409]
