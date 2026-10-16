import importlib
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import Event
from types import ModuleType
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

import pytest
from celery import Celery
from fastapi.testclient import TestClient
from redis import Redis
from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from test_auth_http import csrf_headers
from test_calendar_http import browser_settings as browser_settings
from test_calendar_http import calendar_client as calendar_client
from test_calendar_http import concurrent_engine as concurrent_engine
from test_calendar_http import live_client as live_client
from test_calendar_http import password_hash as password_hash
from test_calendar_http import settings as settings
from test_logging import capture_json
from test_reminders_http import BASE, create, event
from test_schedule_events_http import enrolled as enrolled
from test_schedule_expansion import schedule_fixture
from test_schedule_storage import store as store

from app.core import config
from app.core.config import Settings
from app.modules.academics.application.ports import AcademicProvider
from app.modules.academics.infrastructure.orm import AcademicProfileModel
from app.modules.calendar.infrastructure.orm import PersonalCalendarEventModel
from app.modules.notifications.infrastructure.orm import NotificationModel
from app.modules.reminders.application.delivery import ReminderDispatchUnavailable
from app.modules.reminders.infrastructure.dispatch import dispatch_due
from app.modules.reminders.infrastructure.orm import ReminderModel
from app.modules.reminders.infrastructure.repository import SqlAlchemyReminderRepository
from app.modules.schedule.application.expansion import expand_schedule
from app.modules.schedule.infrastructure.storage import SqlAlchemyScheduleStore
from app.modules.users.infrastructure.orm import UserModel
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication


def sweep(engine: Engine, now: datetime) -> None:
    provider = Mock(spec=AcademicProvider)
    dispatch_due(sessionmaker(engine), provider, now=lambda: now)
    assert provider.mock_calls == []


def state(engine: Engine, reminder: dict) -> tuple[str | None, int]:
    with Session(engine) as database:
        row = database.get(ReminderModel, UUID(reminder["id"]))
        return row.status if row else None, len(list(database.scalars(select(NotificationModel))))


def test_due_boundary_retry_and_current_title(
    calendar_client: TestClient, concurrent_engine: Engine
) -> None:
    target = event(calendar_client)
    reminder = create(calendar_client, target)
    due = datetime.fromisoformat(reminder["due_at"])
    sweep(concurrent_engine, due - timedelta(microseconds=1))
    assert state(concurrent_engine, reminder) == ("pending", 0)
    assert (
        calendar_client.patch(
            f"/api/v1/calendar/personal-events/{target['id']}",
            headers=csrf_headers(calendar_client),
            json={"expected_version": 1, "title": "Updated private title"},
        ).status_code
        == 200
    )
    sweep(concurrent_engine, due)
    sweep(concurrent_engine, due + timedelta(seconds=1))
    assert state(concurrent_engine, reminder) == ("delivered", 1)
    with Session(concurrent_engine) as database:
        item = database.scalar(select(NotificationModel))
        assert item is not None and item.title == "Updated private title"
        assert item.reminder_id == UUID(reminder["id"])
    assert (
        calendar_client.patch(
            f"{BASE}/{reminder['id']}",
            headers=csrf_headers(calendar_client),
            json={"expected_version": 2, "minutes_before": 0},
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "operation", ["cancel", "delete", "move", "delete_event", "disabled", "ended"]
)
def test_obsolete_work_never_notifies(
    calendar_client: TestClient, concurrent_engine: Engine, operation: str
) -> None:
    target = event(calendar_client)
    reminder = create(calendar_client, target)
    due = datetime.fromisoformat(reminder["due_at"])
    path, headers = f"{BASE}/{reminder['id']}", csrf_headers(calendar_client)
    if operation == "cancel":
        assert (
            calendar_client.post(
                path + "/cancel", headers=headers, json={"expected_version": 1}
            ).status_code
            == 200
        )
    elif operation == "delete":
        assert (
            calendar_client.delete(path + "?expected_version=1", headers=headers).status_code == 204
        )
    elif operation == "delete_event":
        assert (
            calendar_client.delete(
                f"/api/v1/calendar/events/{target['id']}", headers=headers
            ).status_code
            == 204
        )
    elif operation == "move":
        start = datetime.fromisoformat(target["starts_at"]) + timedelta(hours=2)
        assert (
            calendar_client.patch(
                f"/api/v1/calendar/events/{target['id']}",
                headers=headers,
                json={
                    "starts_at": start.isoformat(),
                    "ends_at": (start + timedelta(hours=1)).isoformat(),
                },
            ).status_code
            == 200
        )
    elif operation == "disabled":
        with Session(concurrent_engine) as database, database.begin():
            owner = database.scalar(select(UserModel))
            assert owner is not None
            owner.status = "disabled"
    else:
        due = datetime.fromisoformat(target["ends_at"])
    sweep(concurrent_engine, due)
    assert state(concurrent_engine, reminder) == (
        None if operation in {"delete", "delete_event"} else "cancelled",
        0,
    )


def test_edit_replaces_old_trigger_and_broker_gap_catches_up(
    calendar_client: TestClient, concurrent_engine: Engine
) -> None:
    reminder = create(calendar_client)
    old_due = datetime.fromisoformat(reminder["due_at"])
    response = calendar_client.patch(
        f"{BASE}/{reminder['id']}",
        headers=csrf_headers(calendar_client),
        json={"expected_version": 1, "minutes_before": 0},
    )
    assert response.status_code == 200
    sweep(concurrent_engine, old_due)
    assert state(concurrent_engine, reminder) == ("pending", 0)
    # No queued reminder payload is needed after a broker outage; scan committed state again.
    sweep(
        concurrent_engine, datetime.fromisoformat(response.json()["due_at"]) + timedelta(minutes=1)
    )
    assert state(concurrent_engine, reminder) == ("delivered", 1)


def test_failure_rolls_back_notification_and_retry_preserves_other_deliveries(
    calendar_client: TestClient, concurrent_engine: Engine
) -> None:
    first, second = create(calendar_client), create(calendar_client)
    due = max(datetime.fromisoformat(item["due_at"]) for item in (first, second))
    original = SqlAlchemyReminderRepository.save

    def fail(self, reminder, expected_version):
        if reminder.id == UUID(first["id"]):
            raise SQLAlchemyError("private-reminder-data")
        return original(self, reminder, expected_version)

    with patch.object(SqlAlchemyReminderRepository, "save", fail), capture_json() as output:
        with pytest.raises(ReminderDispatchUnavailable):
            sweep(concurrent_engine, due)
    assert "private-reminder-data" not in output.getvalue()
    assert state(concurrent_engine, first) == ("pending", 1)
    assert state(concurrent_engine, second) == ("delivered", 1)
    sweep(concurrent_engine, due)
    assert state(concurrent_engine, first) == ("delivered", 2)


def test_concurrent_sweeps_deliver_once(
    calendar_client: TestClient, concurrent_engine: Engine
) -> None:
    reminder = create(calendar_client)
    due = datetime.fromisoformat(reminder["due_at"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: sweep(concurrent_engine, due), range(2)))
    assert state(concurrent_engine, reminder) == ("delivered", 1)


def test_delivery_waits_for_committed_target_edit(
    calendar_client: TestClient, concurrent_engine: Engine
) -> None:
    reminder = create(calendar_client)
    due = datetime.fromisoformat(reminder["due_at"])
    entered = Event()
    original = SqlAlchemyUserAuthentication.lock_active

    def announce(self, user_id):
        entered.set()
        return original(self, user_id)

    with ThreadPoolExecutor(max_workers=1) as pool:
        with Session(concurrent_engine) as database, database.begin():
            target = database.get(PersonalCalendarEventModel, UUID(reminder["event_id"]))
            assert target is not None
            assert SqlAlchemyUserAuthentication(database).lock_active(target.user_id)
            with patch.object(SqlAlchemyUserAuthentication, "lock_active", announce):
                future = pool.submit(sweep, concurrent_engine, due)
                assert entered.wait(timeout=3)
                target.starts_at += timedelta(hours=2)
                target.ends_at += timedelta(hours=2)
        future.result(timeout=5)
    assert state(concurrent_engine, reminder) == ("cancelled", 0)


@pytest.mark.parametrize("operation", ["hidden", "skip", "withdraw", "profile", "move"])
def test_official_delivery_revalidates_current_calendar(
    enrolled: TestClient, concurrent_engine: Engine, store: SqlAlchemyScheduleStore, operation: str
) -> None:
    now, snapshot = datetime.now(UTC), schedule_fixture()
    lesson = replace(
        expand_schedule(snapshot)[0],
        starts_at=now + timedelta(days=2),
        ends_at=now + timedelta(days=2, hours=1),
        subgroup=1,
    )
    token = store.claim(24066, "353501", now)
    assert token and store.apply(24066, token, snapshot, [lesson], now)
    reminder = create(enrolled, {"id": str(lesson.id)}, source="official")
    if operation in {"hidden", "skip", "move"}:
        values = {"hidden": True} if operation == "hidden" else {"skipped": True}
        if operation == "move":
            values = {
                "starts_at": (lesson.starts_at + timedelta(hours=2)).isoformat(),
                "ends_at": (lesson.ends_at + timedelta(hours=2)).isoformat(),
            }
        assert (
            enrolled.put(
                f"/api/v1/calendar/overrides/{lesson.id}",
                headers=csrf_headers(enrolled),
                json=values,
            ).status_code
            == 200
        )
    elif operation == "profile":
        with Session(concurrent_engine) as database, database.begin():
            profile = database.scalar(select(AcademicProfileModel))
            assert profile is not None
            profile.subgroup = 2
    else:
        token = store.claim(24066, "353501", now + timedelta(hours=2), force=True)
        assert token and store.apply(24066, token, snapshot, [], now + timedelta(hours=2))
    sweep(concurrent_engine, datetime.fromisoformat(reminder["due_at"]))
    assert state(concurrent_engine, reminder) == (
        ("delivered", 1) if operation == "hidden" else ("cancelled", 0)
    )


@pytest.fixture
def reminder_tasks(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> ModuleType:
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    module = importlib.import_module("app.modules.reminders.infrastructure.tasks")
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    return module


def test_worker_registration_retry_and_safe_errors(
    reminder_tasks: ModuleType, concurrent_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    reminder_tasks.celery_app.loader.import_default_modules()
    task = reminder_tasks.dispatch_reminders
    assert "reminders.dispatch_due" in reminder_tasks.celery_app.tasks
    assert reminder_tasks.celery_app.conf.beat_schedule["reminders-dispatch-due"] == {
        "task": "reminders.dispatch_due",
        "schedule": 30.0,
    }
    assert task.acks_late and task.reject_on_worker_lost
    assert task.ignore_result and not task.store_errors_even_if_ignored
    monkeypatch.setattr(reminder_tasks, "create_database_engine", lambda _: concurrent_engine)
    dispatch = Mock(side_effect=[SQLAlchemyError("private-worker-data"), None])
    monkeypatch.setattr(reminder_tasks, "dispatch_due", dispatch)
    with capture_json() as output:
        result = task.apply()
    assert result.successful() and dispatch.call_count == 2
    assert "private-worker-data" not in output.getvalue()
    dispatch.side_effect = SQLAlchemyError("private-worker-data")
    with capture_json() as output:
        result = task.apply()
    assert result.failed() and isinstance(result.result, ReminderDispatchUnavailable)
    assert str(result.result) == "Reminder dispatch is unavailable."
    assert "private-worker-data" not in output.getvalue()


def test_live_queue_message_delivers_committed_reminder_once(
    reminder_tasks: ModuleType,
    calendar_client: TestClient,
    concurrent_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = os.environ.get("AUTH_TEST_REDIS_URL")
    if not url:
        pytest.skip("Set AUTH_TEST_REDIS_URL for a disposable Redis broker.")
    reminder = create(calendar_client)
    due = datetime.fromisoformat(reminder["due_at"])
    monkeypatch.setattr(reminder_tasks, "create_database_engine", lambda _: concurrent_engine)
    monkeypatch.setattr(
        reminder_tasks,
        "dispatch_due",
        lambda sessions, provider: dispatch_due(sessions, provider, now=lambda: due),
    )
    queue = f"ukladen-reminders-test-{uuid4().hex}"
    app = Celery("reminders-test", broker=url)
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        task_ignore_result=True,
        task_default_queue=queue,
        task_default_exchange=queue,
        task_default_routing_key=queue,
        broker_transport_options={"global_keyprefix": f"{queue}:"},
    )
    redis = Redis.from_url(url, socket_connect_timeout=3, socket_timeout=3)
    try:
        app.send_task("reminders.dispatch_due")
        with app.connection_for_read() as connection:
            inbox = connection.SimpleQueue(queue)
            try:
                message = inbox.get(block=False)
                try:
                    assert message.headers["task"] == "reminders.dispatch_due"
                    args, kwargs, _ = message.payload
                    assert args == [] and kwargs == {}
                    assert reminder_tasks.dispatch_reminders.apply(
                        args=args, kwargs=kwargs
                    ).successful()
                    assert reminder_tasks.dispatch_reminders.apply(
                        args=args, kwargs=kwargs
                    ).successful()
                finally:
                    message.ack()
            finally:
                inbox.close()
        assert state(concurrent_engine, reminder) == ("delivered", 1)
    finally:
        keys = list(redis.scan_iter(match=f"{queue}:*"))
        if keys:
            redis.delete(*keys)
        redis.close()
        app.close()
