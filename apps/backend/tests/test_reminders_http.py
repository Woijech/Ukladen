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
from test_calendar_http import live_client as live_client
from test_calendar_http import password_hash as password_hash
from test_calendar_http import settings as settings
from test_logging import capture_json
from test_schedule_events_http import enrolled as enrolled
from test_schedule_expansion import schedule_fixture
from test_schedule_storage import store as store

from app.modules.notifications.domain.notifications import Notification
from app.modules.notifications.infrastructure.repository import SqlAlchemyNotificationRepository
from app.modules.reminders.application.service import ReminderService
from app.modules.reminders.domain.reminders import ReminderConflict
from app.modules.reminders.infrastructure.repository import SqlAlchemyReminderRepository
from app.modules.schedule.application.expansion import expand_schedule
from app.modules.schedule.infrastructure.storage import SqlAlchemyScheduleStore
from app.modules.users.infrastructure.orm import UserModel

BASE = "/api/v1/reminders"
INBOX = "/api/v1/notifications"


def event(client: TestClient) -> dict:
    starts_at = datetime.now(UTC) + timedelta(days=2)
    response = client.post(
        "/api/v1/calendar/personal-events",
        headers=csrf_headers(client),
        json={
            "title": "Private reminder title",
            "starts_at": starts_at.isoformat(),
            "ends_at": (starts_at + timedelta(hours=1)).isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def create(client: TestClient, target: dict | None = None, **values) -> dict:
    target = target or event(client)
    response = client.post(
        BASE,
        headers=csrf_headers(client),
        json={
            "source": "personal",
            "event_id": target["id"],
            "minutes_before": 15,
        }
        | values,
    )
    assert response.status_code == 201, response.text
    return response.json()


def notification(client: TestClient, engine: Engine) -> dict:
    reminder = create(client)
    with Session(engine) as database, database.begin():
        owner = database.scalar(select(UserModel.id))
        assert owner is not None
        SqlAlchemyNotificationRepository(database).create_once(
            Notification(
                id=uuid4(),
                user_id=owner,
                reminder_id=UUID(reminder["id"]),
                source="personal",
                event_id=UUID(reminder["event_id"]),
                title="Private reminder title",
                starts_at=datetime.fromisoformat(reminder["starts_at"]),
                created_at=datetime.now(UTC),
            )
        )
    return client.get(INBOX).json()["items"][0]


def test_crud_versions_cancellation_and_private_logs(calendar_client: TestClient) -> None:
    with capture_json() as output:
        target = event(calendar_client)
        reminder = create(calendar_client, target)
        path, headers = f"{BASE}/{reminder['id']}", csrf_headers(calendar_client)
        assert reminder["status"] == "pending" and reminder["version"] == 1
        assert "user_id" not in reminder
        assert datetime.fromisoformat(reminder["due_at"]) == (
            datetime.fromisoformat(target["starts_at"]) - timedelta(minutes=15)
        )
        assert calendar_client.get(path).json() == reminder
        assert calendar_client.get(BASE).json()["items"] == [reminder]
        assert calendar_client.get(BASE + "?limit=1&offset=1").json()["items"] == []
        changed = calendar_client.patch(
            path, headers=headers, json={"minutes_before": 30, "expected_version": 1}
        )
        assert changed.status_code == 200 and changed.json()["version"] == 2
        assert (
            calendar_client.patch(
                path, headers=headers, json={"minutes_before": 0, "expected_version": 1}
            ).status_code
            == 409
        )
        assert (
            calendar_client.delete(path + "?expected_version=1", headers=headers).status_code == 409
        )
        cancelled = calendar_client.post(
            path + "/cancel", headers=headers, json={"expected_version": 2}
        )
        assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
        assert cancelled.json()["version"] == 3
        assert (
            calendar_client.post(
                path + "/cancel", headers=headers, json={"expected_version": 3}
            ).json()
            == cancelled.json()
        )
        assert (
            calendar_client.patch(
                path, headers=headers, json={"minutes_before": 0, "expected_version": 3}
            ).status_code
            == 409
        )
        assert (
            calendar_client.delete(path + "?expected_version=3", headers=headers).status_code == 204
        )
        assert calendar_client.get(path).status_code == 404
        assert (
            calendar_client.get(f"/api/v1/calendar/personal-events/{target['id']}").status_code
            == 200
        )
    assert "Private reminder title" not in output.getvalue()
    assert calendar_client.get(BASE).headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "changes",
    [
        {"minutes_before": -1},
        {"minutes_before": 43201},
        {"minutes_before": True},
        {"minutes_before": 1.5},
        {"minutes_before": None},
        {"source": "task"},
        {"source": "x"},
        {"user_id": str(uuid4())},
        {"due_at": "2030-01-01T00:00:00Z"},
    ],
)
def test_create_validation(calendar_client: TestClient, changes: dict) -> None:
    target = event(calendar_client)
    response = calendar_client.post(
        BASE,
        headers=csrf_headers(calendar_client),
        json={
            "source": "personal",
            "event_id": target["id"],
            "minutes_before": 15,
        }
        | changes,
    )
    assert response.status_code == 422
    assert calendar_client.get(BASE).json()["items"] == []


def test_past_trigger_and_empty_patch(calendar_client: TestClient) -> None:
    target = event(calendar_client)
    assert (
        calendar_client.post(
            BASE,
            headers=csrf_headers(calendar_client),
            json={
                "source": "personal",
                "event_id": target["id"],
                "minutes_before": 43200,
            },
        ).status_code
        == 422
    )
    reminder = create(calendar_client, target)
    for payload in ({"expected_version": 1}, {"minutes_before": 0, "expected_version": True}):
        assert (
            calendar_client.patch(
                f"{BASE}/{reminder['id']}", headers=csrf_headers(calendar_client), json=payload
            ).status_code
            == 422
        )


def test_owner_isolation_authentication_csrf_and_disabled_owner(
    calendar_client: TestClient, concurrent_engine: Engine, password_hash: str
) -> None:
    reminder = create(calendar_client)
    item = notification(calendar_client, concurrent_engine)
    path, inbox = f"{BASE}/{reminder['id']}", f"{INBOX}/{item['id']}"
    for method, url, payload in (
        ("POST", BASE, {}),
        ("PATCH", path, {"expected_version": 1, "minutes_before": 0}),
        ("POST", path + "/cancel", {"expected_version": 1}),
        ("DELETE", path + "?expected_version=1", None),
        ("POST", inbox + "/read", None),
    ):
        assert calendar_client.request(method, url, json=payload).status_code == 403
    seed_user(concurrent_engine, "other@example.com", password_hash)
    browser_login(calendar_client, "other@example.com")
    headers = csrf_headers(calendar_client)
    assert calendar_client.get(path).status_code == 404
    assert calendar_client.get(BASE).json()["items"] == []
    assert (
        calendar_client.patch(
            path, headers=headers, json={"expected_version": 1, "minutes_before": 0}
        ).status_code
        == 404
    )
    assert calendar_client.delete(path + "?expected_version=1", headers=headers).status_code == 404
    assert (
        calendar_client.post(
            BASE,
            headers=headers,
            json={
                "source": "personal",
                "event_id": reminder["event_id"],
            },
        ).status_code
        == 404
    )
    assert calendar_client.get(INBOX).json()["items"] == []
    assert calendar_client.get(inbox).status_code == 404
    assert calendar_client.post(inbox + "/read", headers=headers).status_code == 404
    with Session(concurrent_engine) as database, database.begin():
        owner = database.scalar(select(UserModel).where(UserModel.email == "other@example.com"))
        assert owner is not None
        owner.status = "disabled"
    assert calendar_client.get(BASE).status_code == 401
    assert calendar_client.get(INBOX).status_code == 401
    calendar_client.cookies.clear()
    assert calendar_client.get(BASE).status_code == 401
    assert calendar_client.get(INBOX).status_code == 401


def test_notification_read_is_idempotent_and_preserves_history(
    calendar_client: TestClient, concurrent_engine: Engine
) -> None:
    item = notification(calendar_client, concurrent_engine)
    path = f"{INBOX}/{item['id']}"
    assert calendar_client.get(path).json() == item
    assert calendar_client.get(INBOX + "?unread_only=true").json()["items"] == [item]
    read = calendar_client.post(path + "/read", headers=csrf_headers(calendar_client))
    assert read.status_code == 200 and read.json()["read_at"] is not None
    assert (
        calendar_client.post(path + "/read", headers=csrf_headers(calendar_client)).json()
        == read.json()
    )
    assert calendar_client.get(INBOX + "?unread_only=true").json()["items"] == []
    assert (
        calendar_client.delete(
            f"/api/v1/calendar/personal-events/{item['event_id']}",
            headers=csrf_headers(calendar_client),
        ).status_code
        == 204
    )
    assert calendar_client.get(path).json() == read.json()


def test_write_failure_rolls_back(calendar_client: TestClient) -> None:
    target = event(calendar_client)
    original = SqlAlchemyReminderRepository.create

    def fail(self, reminder):
        original(self, reminder)
        raise SQLAlchemyError("private-reminder-sql")

    with patch.object(SqlAlchemyReminderRepository, "create", fail), capture_json() as output:
        response = calendar_client.post(
            BASE,
            headers=csrf_headers(calendar_client),
            json={
                "source": "personal",
                "event_id": target["id"],
            },
        )
    assert response.status_code == 503
    assert "private-reminder-sql" not in output.getvalue()
    assert calendar_client.get(BASE).json()["items"] == []


def test_concurrent_updates_have_one_winner(calendar_client: TestClient) -> None:
    reminder = create(calendar_client)
    application = cast(FastAPI, calendar_client.app)

    def change(minutes: int) -> bool:
        with application.state.session_factory() as database, database.begin():
            repository = SqlAlchemyReminderRepository(database)
            # Exercise the shared owner lock and version check without HTTP session serialization.
            from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication

            users = SqlAlchemyUserAuthentication(database)
            owner = database.scalar(select(UserModel.id))
            assert owner is not None
            users.lock_active(owner)
            current = repository.get(owner, UUID(reminder["id"]))
            assert current is not None
            try:
                ReminderService.require_version(current, 1)
            except ReminderConflict:
                return False
            repository.save(
                replace(
                    current,
                    version=2,
                    minutes_before=minutes,
                    due_at=current.starts_at - timedelta(minutes=minutes),
                ),
                1,
            )
            return True

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(change, (10, 20))) == [False, True]


def test_official_targets_respect_subgroups_overrides_and_source_state(
    enrolled: TestClient, store: SqlAlchemyScheduleStore
) -> None:
    now = datetime.now(UTC)
    snapshot = schedule_fixture()
    lesson = replace(
        expand_schedule(snapshot)[0],
        starts_at=now + timedelta(days=2),
        ends_at=now + timedelta(days=2, hours=1),
        subgroup=1,
    )
    foreign = replace(lesson, id=uuid4(), subgroup=2)
    token = store.claim(24066, "353501", now)
    assert token and store.apply(24066, token, snapshot, [lesson, foreign], now)
    headers = csrf_headers(enrolled)
    assert (
        enrolled.post(
            BASE,
            headers=headers,
            json={
                "source": "official",
                "event_id": str(foreign.id),
            },
        ).status_code
        == 404
    )
    override_path = f"/api/v1/calendar/overrides/{lesson.id}"
    assert enrolled.put(override_path, headers=headers, json={"hidden": True}).status_code == 200
    reminder = create(enrolled, {"id": str(lesson.id)}, source="official")
    assert reminder["starts_at"] == lesson.starts_at.isoformat().replace("+00:00", "Z")
    assert (
        enrolled.put(
            override_path, headers=headers, json={"expected_version": 1, "skipped": True}
        ).status_code
        == 200
    )
    assert (
        enrolled.post(
            BASE,
            headers=headers,
            json={
                "source": "official",
                "event_id": str(lesson.id),
            },
        ).status_code
        == 409
    )
    token = store.claim(24066, "353501", now + timedelta(hours=2), force=True)
    assert token and store.apply(24066, token, snapshot, [], now + timedelta(hours=2))
    assert (
        enrolled.post(
            BASE,
            headers=headers,
            json={
                "source": "official",
                "event_id": str(lesson.id),
            },
        ).status_code
        == 409
    )
