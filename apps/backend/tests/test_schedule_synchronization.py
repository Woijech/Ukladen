import importlib
from datetime import UTC, datetime, timedelta
from types import ModuleType
from unittest.mock import Mock, create_autospec

import pytest
from celery import Celery
from sqlalchemy import Engine, event
from test_auth_sessions import concurrent_engine as concurrent_engine
from test_auth_sessions import settings as settings
from test_bsuir_academics import group_fixture
from test_schedule_expansion import schedule_fixture, split_schedule_fixture
from test_schedule_storage import store as store

from app.core import config
from app.core.config import Settings
from app.modules.academics.application.ports import (
    AcademicProviderUnavailable,
    SelectedGroupDirectory,
)
from app.modules.schedule.application.provider import ScheduleProvider
from app.modules.schedule.application.storage import ScheduleState, ScheduleStore
from app.modules.schedule.application.synchronization import (
    ScheduleJobs,
    ScheduleRefreshService,
    ScheduleSyncService,
    ScheduleSyncUnavailable,
)
from app.modules.schedule.infrastructure.jobs import CeleryScheduleJobs
from app.modules.schedule.infrastructure.storage import SqlAlchemyScheduleStore


@pytest.fixture
def tasks(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> ModuleType:
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    module = importlib.import_module("app.modules.schedule.infrastructure.tasks")
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    return module


def test_sync_network_runs_after_claim_commit_and_errors_keep_events(
    store: SqlAlchemyScheduleStore,
    concurrent_engine: Engine,
) -> None:
    transactions: list[str] = []

    def begin(connection):
        transactions.append("begin")

    def commit(connection):
        transactions.append("commit")

    event.listen(concurrent_engine, "begin", begin)
    event.listen(concurrent_engine, "commit", commit)
    provider = create_autospec(ScheduleProvider, instance=True)

    def fetch(group_number: str):
        assert transactions[-1] == "commit"
        return schedule_fixture()

    provider.get_group_schedule.side_effect = fetch
    now = datetime.now(UTC)
    service = ScheduleSyncService(provider, store, lambda: now)
    try:
        assert service.sync(24066, "353501").status == "ready"
        now += timedelta(hours=2)
        provider.get_group_schedule.side_effect = AcademicProviderUnavailable(
            "private upstream data"
        )
        state = service.sync(24066, "353501")
        assert state.status == "error" and state.error_code == "source_unavailable"
        assert state.last_success_at and state.last_success_at < now
        assert (
            len(
                store.events(
                    24066, datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 10, 1, tzinfo=UTC), None
                )
            )
            == 2
        )
    finally:
        event.remove(concurrent_engine, "begin", begin)
        event.remove(concurrent_engine, "commit", commit)


@pytest.mark.parametrize("failure", ["identity", "unsupported", "unpublished"])
def test_source_states_are_explicit(store: SqlAlchemyScheduleStore, failure: str) -> None:
    snapshot = schedule_fixture()
    if failure == "identity":
        assert snapshot.group
        snapshot = snapshot.model_copy(
            update={"group": snapshot.group.model_copy(update={"id": 9})}
        )
    elif failure == "unsupported":
        assert snapshot.schedules
        lesson = snapshot.schedules["Понедельник"][0].model_copy(update={"announcement": True})
        snapshot = snapshot.model_copy(update={"schedules": {"Понедельник": [lesson]}})
    provider = Mock(spec=ScheduleProvider)
    provider.get_group_schedule.return_value = None if failure == "unpublished" else snapshot
    state = ScheduleSyncService(provider, store).sync(24066, "353501")
    assert (
        state.status
        == {"identity": "error", "unsupported": "unsupported", "unpublished": "unpublished"}[
            failure
        ]
    )


def test_split_import_is_complete_replay_safe_and_keeps_last_valid_data(
    store: SqlAlchemyScheduleStore,
) -> None:
    snapshot = split_schedule_fixture()
    provider = Mock(spec=ScheduleProvider)
    provider.get_group_schedule.return_value = snapshot
    now = datetime.now(UTC)
    service = ScheduleSyncService(provider, store, lambda: now)
    start, end = datetime(2026, 9, 1, tzinfo=UTC), datetime(2027, 1, 1, tzinfo=UTC)

    assert service.sync(24066, "353501").status == "ready"
    saved = store.events(24066, start, end, None)
    assert len(saved) == 20
    for subgroup, count in [(1, 12), (2, 10)]:
        selected = store.events(24066, start, end, subgroup)
        assert len(selected) == count
        assert {event.subgroup for event in selected} == {0, subgroup}

    now += timedelta(hours=2)
    assert service.sync(24066, "353501").status == "ready"
    assert [event.id for event in store.events(24066, start, end, None)] == [
        event.id for event in saved
    ]

    assert snapshot.schedules
    invalid = snapshot.schedules["Среда"][0].model_copy(update={"week_numbers": []})
    provider.get_group_schedule.return_value = snapshot.model_copy(
        update={"schedules": {"Среда": [invalid]}}
    )
    now += timedelta(hours=2)
    assert service.sync(24066, "353501").status == "unsupported"
    assert [event.id for event in store.events(24066, start, end, None)] == [
        event.id for event in saved
    ]


def test_refresh_only_queues_due_selected_groups() -> None:
    now = datetime.now(UTC)
    groups = Mock(spec=SelectedGroupDirectory)
    groups.selected_groups.return_value = [group_fixture()]
    store = Mock(spec=ScheduleStore)
    jobs = Mock(spec=ScheduleJobs)
    service = ScheduleRefreshService(groups, store, jobs, 3600, lambda: now)
    store.state.return_value = ScheduleState(24066, "353501", "ready", now, now)
    service.refresh()
    jobs.request_sync.assert_not_called()
    store.state.return_value = ScheduleState(24066, "353501", "syncing", now - timedelta(minutes=3))
    service.refresh()
    jobs.request_sync.assert_called_once_with(24066, "353501")


def test_queue_acceptance_validation_and_safe_failure() -> None:
    celery = create_autospec(Celery, instance=True)
    jobs = CeleryScheduleJobs(celery)
    jobs.request_sync(24066, "353501", force=True)
    celery.send_task.assert_called_once_with(
        "schedule.sync_group",
        kwargs={"group_id": 24066, "group_number": "353501", "force": True},
        ignore_result=True,
        retry=False,
        expires=120,
    )
    for broken in [CeleryScheduleJobs(celery, enabled=False), jobs]:
        celery.send_task.side_effect = RuntimeError("private broker details")
        with pytest.raises(ScheduleSyncUnavailable) as error:
            broken.request_sync(24066, "353501")
        assert "private" not in str(error.value) and error.value.__suppress_context__
    celery.send_task.reset_mock()
    with pytest.raises(ScheduleSyncUnavailable):
        jobs.request_sync(-1, "353501")
    celery.send_task.assert_not_called()


def test_worker_registration_and_execution(
    tasks: ModuleType,
    concurrent_engine: Engine,
    store: SqlAlchemyScheduleStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = Mock(spec=ScheduleProvider)
    provider.get_group_schedule.return_value = schedule_fixture()
    monkeypatch.setattr(tasks, "create_database_engine", lambda _: concurrent_engine)
    monkeypatch.setattr(tasks, "IisPublicProvider", lambda _: provider)
    tasks.celery_app.loader.import_default_modules()
    assert "schedule.sync_group" in tasks.celery_app.tasks
    assert (
        tasks.celery_app.conf.beat_schedule["schedule-refresh-selected"]["task"]
        == "schedule.refresh_selected"
    )
    result = tasks.sync_group.apply(kwargs={"group_id": 24066, "group_number": "353501"})
    assert result.successful() and result.get() is None
    assert store.state(24066, "353501").status == "ready"
    assert tasks.sync_group.ignore_result and not tasks.sync_group.store_errors_even_if_ignored


def test_worker_disabled_and_invalid_jobs_do_not_connect(
    tasks: ModuleType,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = Mock(side_effect=AssertionError("must not connect"))
    monkeypatch.setattr(tasks, "create_database_engine", engine)
    monkeypatch.setattr(
        tasks, "get_settings", lambda: settings.model_copy(update={"schedule_sync_enabled": False})
    )
    result = tasks.sync_group.apply(kwargs={"group_id": 24066, "group_number": "353501"})
    assert result.successful()
    assert tasks.refresh_selected.apply().successful()
    invalid = tasks.sync_group.apply(kwargs={"group_id": -1, "group_number": "353501"})
    assert invalid.failed() and isinstance(invalid.result, ScheduleSyncUnavailable)
    engine.assert_not_called()


def test_periodic_worker_discovers_selected_group_once_and_publishes_after_commit(
    tasks: ModuleType,
    concurrent_engine: Engine,
    store: SqlAlchemyScheduleStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy.orm import Session

    from app.modules.academics.infrastructure.orm import AcademicProfileModel
    from app.modules.users.infrastructure.orm import UserModel

    with Session(concurrent_engine) as database, database.begin():
        users = [UserModel(email="first@example.com"), UserModel(email="second@example.com")]
        database.add_all(users)
        database.flush()
        database.add_all([AcademicProfileModel(user_id=user.id, group_id=24066) for user in users])
    transactions: list[str] = []

    def begin(connection):
        transactions.append("begin")

    def commit(connection):
        transactions.append("commit")

    def publish(group_id, group_number, **kwargs):
        assert transactions[-1] == "commit"

    jobs = Mock(spec=ScheduleJobs)
    jobs.request_sync.side_effect = publish
    monkeypatch.setattr(tasks, "create_database_engine", lambda _: concurrent_engine)
    monkeypatch.setattr(tasks, "CeleryScheduleJobs", lambda _: jobs)
    event.listen(concurrent_engine, "begin", begin)
    event.listen(concurrent_engine, "commit", commit)
    try:
        result = tasks.refresh_selected.apply()
        assert result.successful()
        jobs.request_sync.assert_called_once_with(24066, "353501")
    finally:
        event.remove(concurrent_engine, "begin", begin)
        event.remove(concurrent_engine, "commit", commit)


def test_live_queue_round_trip_to_persisted_events(
    tasks: ModuleType,
    concurrent_engine: Engine,
    store: SqlAlchemyScheduleStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import os
    from uuid import uuid4

    from redis import Redis

    url = os.environ.get("AUTH_TEST_REDIS_URL")
    if not url:
        pytest.skip("Set AUTH_TEST_REDIS_URL for a disposable Redis broker.")
    queue = f"ukladen-schedule-test-{uuid4().hex}"
    prefix = f"{queue}:"
    app = Celery("schedule-test", broker=url)
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        task_ignore_result=True,
        task_default_queue=queue,
        task_default_exchange=queue,
        task_default_routing_key=queue,
        broker_transport_options={"global_keyprefix": prefix},
    )
    redis = Redis.from_url(url, socket_connect_timeout=3, socket_timeout=3)
    provider = Mock(spec=ScheduleProvider)
    provider.get_group_schedule.return_value = schedule_fixture()
    monkeypatch.setattr(tasks, "create_database_engine", lambda _: concurrent_engine)
    monkeypatch.setattr(tasks, "IisPublicProvider", lambda _: provider)
    try:
        CeleryScheduleJobs(app).request_sync(24066, "353501", force=True)
        with app.connection_for_read() as connection:
            inbox = connection.SimpleQueue(queue)
            try:
                message = inbox.get(block=False)
                try:
                    assert message.headers["task"] == "schedule.sync_group"
                    args, payload, _ = message.payload
                    result = tasks.sync_group.apply(args=args, kwargs=payload)
                    assert result.successful() and store.state(24066, "353501").status == "ready"
                finally:
                    message.ack()
            finally:
                inbox.queue.delete()
                inbox.close()
    finally:
        app.close()
        keys = list(redis.scan_iter(match=f"{prefix}*"))
        if keys:
            redis.delete(*keys)
        redis.close()
