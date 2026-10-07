from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from test_auth_http import browser_login, csrf_headers, seed_user
from test_auth_http import browser_settings as browser_settings
from test_auth_http import live_client as live_client
from test_auth_login import password_hash as password_hash
from test_auth_sessions import concurrent_engine as concurrent_engine
from test_auth_sessions import settings as settings
from test_bsuir_public_api import response_for
from test_schedule_expansion import schedule_fixture
from test_schedule_storage import store as store

from app.integrations.bsuir.public_api import IisPublicProvider
from app.modules.academics.infrastructure.orm import AcademicProfileModel
from app.modules.schedule.application.expansion import expand_schedule
from app.modules.schedule.application.synchronization import ScheduleJobs, ScheduleSyncUnavailable
from app.modules.schedule.infrastructure.storage import SqlAlchemyScheduleStore

BASE = "/api/v1/schedule"
RANGE = "?date_from=2026-09-01&date_to=2026-09-30"


@pytest.fixture
def enrolled(
    live_client: TestClient,
    concurrent_engine: Engine,
    password_hash: str,
    store: SqlAlchemyScheduleStore,
) -> Iterator[TestClient]:
    application = cast(FastAPI, live_client.app)
    seed_user(concurrent_engine, "student@example.com", password_hash)
    browser_login(live_client)
    with httpx.Client(transport=httpx.MockTransport(response_for)) as transport:
        application.state.academic_provider = IisPublicProvider(transport)
        response = live_client.patch(
            "/api/v1/academics/me",
            headers=csrf_headers(live_client),
            json={"group_id": 24066, "subgroup": 1},
        )
        assert response.status_code == 200
    application.state.schedule_provider = Mock(side_effect=AssertionError("No live reads"))
    application.state.schedule_jobs = Mock(spec=ScheduleJobs)
    yield live_client


def test_saved_events_are_read_offline_with_subgroup_and_source_state(
    enrolled: TestClient,
    store: SqlAlchemyScheduleStore,
) -> None:
    before = enrolled.get(f"{BASE}/me/events{RANGE}")
    assert before.status_code == 200 and before.json()["events"] == []
    assert before.json()["source"]["status"] == "not_synced"
    snapshot = schedule_fixture()
    original = expand_schedule(snapshot)
    first = replace(original[0], subgroup=0)
    own = replace(original[0], id=uuid4(), subgroup=1)
    other = replace(original[0], id=uuid4(), subgroup=2)
    now = datetime.now(UTC)
    token = store.claim(24066, "353501", now)
    assert token and store.apply(24066, token, snapshot, [first, own, other], now)
    response = enrolled.get(f"{BASE}/me/events{RANGE}")
    assert response.status_code == 200
    assert sorted(row["subgroup"] for row in response.json()["events"]) == [0, 1]
    assert response.json()["source"]["status"] == "ready"
    assert response.headers["cache-control"] == "no-store"
    assert enrolled.get(f"{BASE}/events/{own.id}").status_code == 200
    assert enrolled.get(f"{BASE}/events/{other.id}").status_code == 404
    assert enrolled.get(f"{BASE}/events/{uuid4()}").status_code == 404
    group = enrolled.get(f"{BASE}/groups/353501/events{RANGE}&subgroup=2")
    assert group.status_code == 200 and sorted(
        row["subgroup"] for row in group.json()["events"]
    ) == [0, 2]
    assert enrolled.get(f"{BASE}/me/sync-status").json()["status"] == "ready"


def test_sync_requires_csrf_and_handles_rate_limit_and_broker_failure(enrolled: TestClient) -> None:
    application = cast(FastAPI, enrolled.app)
    jobs = application.state.schedule_jobs
    assert enrolled.post(f"{BASE}/me/sync").status_code == 403
    response = enrolled.post(f"{BASE}/me/sync", headers=csrf_headers(enrolled))
    assert response.status_code == 202 and response.json()["group_id"] == 24066
    jobs.request_sync.assert_called_once_with(24066, "353501", force=True)
    application.state.rate_limiter.check.return_value = (False, 42)
    blocked = enrolled.post(f"{BASE}/me/sync", headers=csrf_headers(enrolled))
    assert blocked.status_code == 429 and blocked.headers["retry-after"] == "42"
    application.state.rate_limiter.check.return_value = (True, 60)
    jobs.request_sync.side_effect = ScheduleSyncUnavailable("private broker details")
    unavailable = enrolled.post(f"{BASE}/me/sync", headers=csrf_headers(enrolled))
    assert unavailable.status_code == 503 and "private" not in unavailable.text


@pytest.mark.parametrize(
    "query",
    [
        "?date_from=2026-09-30&date_to=2026-09-01",
        "?date_from=2026-01-01&date_to=2027-01-02",
        "?date_from=invalid&date_to=2026-09-30",
        "?date_from=2026-09-01",
    ],
)
def test_date_range_validation(enrolled: TestClient, query: str) -> None:
    assert enrolled.get(f"{BASE}/me/events{query}").status_code == 422


def test_missing_profile_and_sessions_are_rejected(
    enrolled: TestClient,
    concurrent_engine: Engine,
) -> None:
    with Session(concurrent_engine) as database, database.begin():
        profile = database.query(AcademicProfileModel).one()
        database.delete(profile)
    assert enrolled.get(f"{BASE}/me/events{RANGE}").status_code == 409
    assert enrolled.post(f"{BASE}/me/sync", headers=csrf_headers(enrolled)).status_code == 409
    enrolled.cookies.clear()
    assert enrolled.get(f"{BASE}/me/sync-status").status_code == 401
    assert enrolled.get(f"{BASE}/groups/353501/events{RANGE}").status_code == 401
