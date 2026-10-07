from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from test_auth_persistence import database_connection as database_connection
from test_auth_persistence import test_migration_round_trip as test_migration_round_trip
from test_auth_sessions import concurrent_engine as concurrent_engine
from test_bsuir_academics import group_fixture
from test_schedule_expansion import schedule_fixture

from app.db.session import create_session_factory
from app.modules.academics.infrastructure.orm import UniversityGroupModel
from app.modules.schedule.application.expansion import expand_schedule
from app.modules.schedule.infrastructure.orm import OfficialScheduleEventModel, ScheduleSourceModel
from app.modules.schedule.infrastructure.storage import SqlAlchemyScheduleStore


@pytest.fixture
def store(concurrent_engine: Engine) -> SqlAlchemyScheduleStore:
    from dataclasses import asdict

    with Session(concurrent_engine) as database, database.begin():
        database.add(UniversityGroupModel(**asdict(group_fixture())))
    return SqlAlchemyScheduleStore(create_session_factory(concurrent_engine))


def test_import_preserves_ids_reconciles_changes_and_keeps_withdrawn_history(
    store: SqlAlchemyScheduleStore,
) -> None:
    now = datetime.now(UTC)
    snapshot = schedule_fixture()
    events = expand_schedule(snapshot)
    token = store.claim(24066, "353501", now)
    assert token and store.apply(24066, token, snapshot, events, now)
    stored = store.events(24066, events[0].starts_at, events[-1].ends_at, None)
    original_ids = [event.id for event in stored]
    assert original_ids == [event.id for event in events]
    # A repeated import has fresh transient UUIDs; persisted IDs must stay the same.
    now += timedelta(hours=2)
    token = store.claim(24066, "353501", now)
    assert token and store.apply(24066, token, snapshot, expand_schedule(snapshot), now)
    assert [
        event.id for event in store.events(24066, events[0].starts_at, events[-1].ends_at, None)
    ] == original_ids
    now += timedelta(hours=2)
    token = store.claim(24066, "353501", now)
    moved = replace(
        events[0],
        id=uuid4(),
        starts_at=events[0].starts_at + timedelta(hours=1),
        ends_at=events[0].ends_at + timedelta(hours=1),
        rooms=("new room",),
    )
    assert token and store.apply(24066, token, snapshot, [moved], now)
    saved = store.event(original_ids[0])
    assert saved and saved.active and saved.rooms == ("new room",)
    withdrawn = store.event(original_ids[1])
    assert withdrawn and not withdrawn.active
    # A changed date is a new occurrence; never guess where a user's override belongs.
    now += timedelta(hours=2)
    token = store.claim(24066, "353501", now)
    other_day = replace(
        moved,
        id=uuid4(),
        starts_at=moved.starts_at + timedelta(days=1),
        ends_at=moved.ends_at + timedelta(days=1),
    )
    assert token and store.apply(24066, token, snapshot, [other_day], now)
    retired = store.event(original_ids[0])
    assert retired and not retired.active and store.event(other_day.id)


def test_leases_fence_late_workers_and_recover_expired_claims(
    store: SqlAlchemyScheduleStore,
) -> None:
    now = datetime.now(UTC)
    token = store.claim(24066, "353501", now)
    assert token
    assert store.claim(24066, "353501", now + timedelta(seconds=1), force=True) is None
    later = now + timedelta(minutes=3)
    replacement = store.claim(24066, "353501", later)
    assert replacement and replacement != token
    assert not store.apply(24066, token, None, [], later)
    store.fail(24066, token, "source_unavailable", later)
    assert store.state(24066, "353501").status == "syncing"
    snapshot = schedule_fixture()
    assert store.apply(24066, replacement, snapshot, expand_schedule(snapshot), later)
    assert store.state(24066, "353501").status == "ready"


def test_failed_import_preserves_snapshot_and_events_and_unpublished_retires_them(
    store: SqlAlchemyScheduleStore,
    concurrent_engine: Engine,
) -> None:
    now = datetime.now(UTC)
    snapshot = schedule_fixture()
    events = expand_schedule(snapshot)
    token = store.claim(24066, "353501", now)
    assert token and store.apply(24066, token, snapshot, events, now)
    now += timedelta(hours=2)
    token = store.claim(24066, "353501", now)
    assert token
    store.fail(24066, token, "unsupported_schedule", now)
    assert store.state(24066, "353501").status == "unsupported"
    assert len(store.events(24066, events[0].starts_at, events[-1].ends_at, None)) == 2
    with Session(concurrent_engine) as database:
        row = database.get(ScheduleSourceModel, 24066)
        assert row and row.snapshot == snapshot.model_dump(mode="json")
    now += timedelta(hours=2)
    token = store.claim(24066, "353501", now)
    assert token and store.apply(24066, token, None, [], now)
    assert store.state(24066, "353501").status == "unpublished"
    assert store.events(24066, events[0].starts_at, events[-1].ends_at, None) == []
    with Session(concurrent_engine) as database:
        assert len(list(database.scalars(select(OfficialScheduleEventModel)))) == 2


def test_ambiguous_parallel_lessons_never_share_identity(store: SqlAlchemyScheduleStore) -> None:
    now = datetime.now(UTC)
    snapshot = schedule_fixture()
    first = expand_schedule(snapshot)[0]
    second = replace(first, id=uuid4(), rooms=("parallel room",))
    token = store.claim(24066, "353501", now)
    assert token and store.apply(24066, token, snapshot, [first, second], now)
    now += timedelta(hours=2)
    third = replace(first, id=uuid4(), rooms=("changed room",))
    token = store.claim(24066, "353501", now)
    assert token and store.apply(24066, token, snapshot, [third, second], now)
    assert store.event(third.id)
    saved = store.event(second.id)
    retired = store.event(first.id)
    assert saved and saved.active and retired and not retired.active


def test_concurrent_claims_only_allow_one_worker(store: SqlAlchemyScheduleStore) -> None:
    from concurrent.futures import ThreadPoolExecutor

    now = datetime.now(UTC)
    with ThreadPoolExecutor(max_workers=2) as workers:
        claims = list(workers.map(lambda _: store.claim(24066, "353501", now), range(2)))
    assert len([claim for claim in claims if claim is not None]) == 1
