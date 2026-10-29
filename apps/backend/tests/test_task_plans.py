from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_auth_http import csrf_headers
from test_calendar_http import browser_settings as browser_settings
from test_calendar_http import calendar_client as calendar_client
from test_calendar_http import concurrent_engine as concurrent_engine
from test_calendar_http import enrolled as enrolled
from test_calendar_http import live_client as live_client
from test_calendar_http import password_hash as password_hash
from test_calendar_http import settings as settings
from test_calendar_http import store as store
from test_task_work_planning import PLANNING, START, session_payload
from test_tasks_http import BASE, create_task
from test_tasks_service import setup_service

from app.modules.calendar.domain.availability import TimeInterval
from app.modules.tasks.domain.planner import plan_work
from app.modules.tasks.domain.planning import WorkPreferences, WorkSession
from app.modules.tasks.infrastructure.planning import SqlAlchemyPlanning, WorkSessionModel
from app.modules.tasks.infrastructure.plans import TaskPlanModel


def proposal(client, tasks, minutes=180, **extra):
    values = {
        "starts_at": START.isoformat(),
        "ends_at": (START + timedelta(minutes=minutes)).isoformat(),
        "task_ids": [task["id"] for task in tasks],
        "windows": [
            {
                "starts_at": START.isoformat(),
                "ends_at": (START + timedelta(minutes=minutes)).isoformat(),
            }
        ],
    } | extra
    response = client.post(PLANNING + "/plans", headers=csrf_headers(client), json=values)
    assert response.status_code == 200, response.text
    return response.json()


def apply(client, plan, **extra):
    return client.post(
        PLANNING + "/plans/" + plan["id"] + "/apply",
        headers=csrf_headers(client),
        json={"digest": plan["digest"]} | extra,
    )


def test_planner_orders_dependencies_breaks_and_small_final_remainder():
    service, _, _ = setup_service()
    owner = uuid4()
    parent = service.create(owner, {"title": "Parent", "remaining_minutes": 999})
    a = service.create(owner, {"title": "A", "remaining_minutes": 50, "parent_id": None})
    a = replace(a, parent_id=parent.id)
    b = service.create(owner, {"title": "B", "remaining_minutes": 45, "priority": "urgent"})
    window = TimeInterval(START, START + timedelta(hours=3))
    result = plan_work(
        [parent, a, b],
        [(b.id, a.id)],
        {parent.id, b.id},
        [window],
        [],
        [],
        [],
        WorkPreferences(),
        START - timedelta(days=1),
    )
    assert not result.unplaced
    assert [item.task_id for item in result.sessions] == [a.id, a.id, b.id]
    assert [(item.ends_at - item.starts_at).total_seconds() / 60 for item in result.sessions] == [
        45,
        5,
        45,
    ]
    assert result.sessions[2].starts_at >= result.sessions[1].ends_at + timedelta(minutes=15)


def test_planner_unknown_remaining_dependencies_partial_and_pinned():
    service, _, _ = setup_service()
    owner = uuid4()
    a = service.create(owner, {"title": "A", "remaining_minutes": 90})
    b = service.create(owner, {"title": "B"})
    window = TimeInterval(START, START + timedelta(minutes=60))
    result = plan_work(
        [a, b], [], {a.id, b.id}, [window], [], [], [], WorkPreferences(), START - timedelta(days=1)
    )
    assert {(item.task_id, item.minutes, item.reason) for item in result.unplaced} == {
        (a.id, 45, "not_placed_in_allowed_windows"),
        (b.id, None, "remaining_work_required"),
    }
    unresolved = plan_work(
        [a, b],
        [(a.id, b.id)],
        {a.id},
        [window],
        [],
        [],
        [],
        WorkPreferences(),
        START - timedelta(days=1),
    )
    assert unresolved.unplaced[0].reason == "unresolved_dependencies"
    fixed = WorkSession(
        id=uuid4(),
        user_id=owner,
        task_id=a.id,
        starts_at=START,
        ends_at=START + timedelta(minutes=45),
        pinned=True,
    )
    result = plan_work(
        [a], [], {a.id}, [window], [], [fixed], [], WorkPreferences(), START - timedelta(days=1)
    )
    assert not result.sessions and result.unplaced[0].minutes == 45


def test_plan_partial_confirmation_and_replay_survive_task_changes(calendar_client: TestClient):
    client = calendar_client
    task = create_task(client, remaining_minutes=90)
    plan = proposal(client, [task], minutes=60)
    assert plan["verified"] and plan["unplaced"][0]["minutes"] == 45
    assert apply(client, plan).status_code == 409
    accepted = apply(client, plan, accept_partial=True)
    assert accepted.status_code == 200 and accepted.json()["status"] == "applied"
    client.patch(
        BASE + "/" + task["id"],
        headers=csrf_headers(client),
        json={"expected_version": 1, "remaining_minutes": 10},
    )
    replay = apply(client, plan)
    assert replay.status_code == 200 and replay.json() == accepted.json()
    sessions = client.get(
        PLANNING + "/sessions",
        params={"starts_at": START.isoformat(), "ends_at": (START + timedelta(days=1)).isoformat()},
    ).json()
    assert len(sessions) == 1


@pytest.mark.parametrize("changed", ["task", "preferences", "calendar", "session"])
def test_plan_revalidates_all_preconditions(calendar_client: TestClient, changed: str):
    client = calendar_client
    task = create_task(client, remaining_minutes=90)
    plan = proposal(client, [task])
    headers = csrf_headers(client)
    if changed == "task":
        client.patch(
            BASE + "/" + task["id"],
            headers=headers,
            json={"expected_version": 1, "remaining_minutes": 100},
        )
    elif changed == "preferences":
        client.put(
            PLANNING + "/preferences",
            headers=headers,
            json={"expected_version": 0, "windows": [], "session_minutes": 30},
        )
    elif changed == "calendar":
        client.post(
            "/api/v1/calendar/personal-events",
            headers=headers,
            json={
                "title": "Appointment",
                "starts_at": START.isoformat(),
                "ends_at": (START + timedelta(minutes=30)).isoformat(),
            },
        )
    else:
        client.post(PLANNING + "/sessions", headers=headers, json=session_payload(client, task))
    rejected = apply(client, plan)
    assert rejected.status_code == 409
    assert client.get(PLANNING + "/plans/" + plan["id"]).json()["status"] == "pending"


def test_replan_preserves_suitable_manual_sessions_and_pins(calendar_client: TestClient):
    client = calendar_client
    task = create_task(client, remaining_minutes=90)
    first = client.post(
        PLANNING + "/sessions", headers=csrf_headers(client), json=session_payload(client, task)
    ).json()
    second = client.post(
        PLANNING + "/sessions",
        headers=csrf_headers(client),
        json=session_payload(
            client, task, START + timedelta(hours=1), START + timedelta(hours=1, minutes=45)
        )
        | {"pinned": True},
    ).json()
    plan = proposal(client, [task], replan=True)
    assert plan["cancelled_sessions"] == []
    assert [item["retained_id"] for item in plan["sessions"]] == [first["id"]]
    assert apply(client, plan).status_code == 200
    # Force the unpinned manual session to move; the pinned session remains protected.
    client.post(
        "/api/v1/calendar/personal-events",
        headers=csrf_headers(client),
        json={
            "title": "Busy",
            "starts_at": START.isoformat(),
            "ends_at": (START + timedelta(minutes=45)).isoformat(),
        },
    )
    plan = proposal(client, [task], minutes=240, replan=True)
    assert plan["cancelled_sessions"] == [first["id"]]
    assert second["id"] not in plan["cancelled_sessions"]
    assert apply(client, plan).status_code == 200


def test_whole_plan_rolls_back_and_concurrent_confirmation_replays(
    calendar_client: TestClient, concurrent_engine: Engine
):
    client = calendar_client
    task = create_task(client, remaining_minutes=90)
    plan = proposal(client, [task])
    original = SqlAlchemyPlanning.put_session
    count = 0

    def fail(self, value):
        nonlocal count
        original(self, value)
        count += 1
        if count == 2:
            raise RuntimeError("synthetic write failure")

    with (
        patch.object(SqlAlchemyPlanning, "put_session", fail),
        pytest.raises(RuntimeError, match="synthetic"),
    ):
        apply(client, plan)
    with Session(concurrent_engine) as database:
        assert list(database.scalars(select(WorkSessionModel))) == []
        row = database.get(TaskPlanModel, UUID(plan["id"]))
        assert row is not None and row.status == "pending"
    headers = csrf_headers(client)

    def confirm(_):
        return client.post(
            PLANNING + "/plans/" + plan["id"] + "/apply",
            headers=headers,
            json={"digest": plan["digest"]},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as workers:
        assert list(workers.map(confirm, range(2))) == [200, 200]
    with Session(concurrent_engine) as database:
        assert len(list(database.scalars(select(WorkSessionModel)))) == 2


def test_expected_iis_coverage_is_conditional_and_ownership_csrf(enrolled: TestClient):
    client = enrolled
    task = create_task(client, remaining_minutes=45)
    plan = proposal(client, [task])
    assert not plan["verified"] and "schedule_coverage_unknown" in plan["warnings"]
    assert apply(client, plan).status_code == 409
    assert (
        client.post(
            PLANNING + "/plans/" + plan["id"] + "/apply", json={"digest": plan["digest"]}
        ).status_code
        == 403
    )
    assert client.get(PLANNING + "/plans/" + str(uuid4())).status_code == 404


def test_deadline_partial_work_never_unblocks_its_successor():
    service, _, _ = setup_service()
    owner = uuid4()
    predecessor = service.create(
        owner,
        {
            "title": "Before deadline",
            "remaining_minutes": 90,
            "deadline_at": START + timedelta(minutes=60),
        },
    )
    successor = service.create(
        owner, {"title": "After predecessor", "remaining_minutes": 30, "priority": "urgent"}
    )
    result = plan_work(
        [predecessor, successor],
        [(successor.id, predecessor.id)],
        {predecessor.id, successor.id},
        [TimeInterval(START, START + timedelta(hours=4))],
        [],
        [],
        [],
        WorkPreferences(),
        START - timedelta(hours=1),
    )
    assert len(result.sessions) == 1 and result.sessions[0].task_id == predecessor.id
    assert predecessor.deadline_at is not None
    assert result.sessions[0].ends_at <= predecessor.deadline_at
    assert {(item.task_id, item.minutes, item.reason) for item in result.unplaced} == {
        (predecessor.id, 45, "not_placed_in_allowed_windows"),
        (successor.id, 30, "unresolved_dependencies"),
    }
    assert predecessor.remaining_minutes == 90 and successor.remaining_minutes == 30


def test_elapsed_sessions_do_not_reduce_explicit_remaining_work():
    service, _, _ = setup_service()
    owner = uuid4()
    task = service.create(owner, {"title": "Missed session", "remaining_minutes": 45})
    old = WorkSession(
        id=uuid4(),
        user_id=owner,
        task_id=task.id,
        starts_at=START - timedelta(days=1),
        ends_at=START - timedelta(days=1) + timedelta(minutes=45),
    )
    result = plan_work(
        [task],
        [],
        {task.id},
        [TimeInterval(START, START + timedelta(hours=2))],
        [],
        [old],
        [],
        WorkPreferences(),
        START - timedelta(hours=1),
    )
    assert not result.unplaced and len(result.sessions) == 1
    assert (result.sessions[0].ends_at - result.sessions[0].starts_at).total_seconds() == 45 * 60
    assert task.remaining_minutes == 45


def test_two_independent_plans_cannot_reserve_the_same_snapshot(
    calendar_client: TestClient, concurrent_engine: Engine
):
    client = calendar_client
    task = create_task(client, remaining_minutes=90)
    plans = [proposal(client, [task]), proposal(client, [task])]
    headers = csrf_headers(client)

    def confirm(plan):
        return client.post(
            PLANNING + "/plans/" + plan["id"] + "/apply",
            headers=headers,
            json={"digest": plan["digest"]},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(workers.map(confirm, plans)) == [200, 409]
    with Session(concurrent_engine) as database:
        assert len(list(database.scalars(select(WorkSessionModel)))) == 2
