from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_auth_http import csrf_headers
from test_calendar_http import browser_settings as browser_settings
from test_calendar_http import calendar_client as calendar_client
from test_calendar_http import concurrent_engine as concurrent_engine
from test_calendar_http import enrolled as enrolled
from test_calendar_http import live_client as live_client
from test_calendar_http import password_hash as password_hash
from test_calendar_http import settings as settings
from test_calendar_http import store as store
from test_tasks_http import create_task

PATH = "/api/v1/calendar/availability"
START, END = "2026-10-07T09:00:00Z", "2026-10-07T12:00:00Z"
PAYLOAD = {
    "starts_at": START,
    "ends_at": END,
    "windows": [{"starts_at": START, "ends_at": END}],
    "candidates": [{"starts_at": "2026-10-07T10:30:00Z", "ends_at": "2026-10-07T11:00:00Z"}],
}


def test_availability_http_complete_personal_busy_set_nonblocking_and_owned_exclusion(
    calendar_client: TestClient,
) -> None:
    client = calendar_client
    headers = csrf_headers(client)
    event = client.post(
        "/api/v1/calendar/personal-events",
        headers=headers,
        json={
            "title": "Training",
            "starts_at": "2026-10-07T10:00:00Z",
            "ends_at": "2026-10-07T11:00:00Z",
        },
    ).json()
    nonblocking = client.post(
        "/api/v1/calendar/personal-events",
        headers=headers,
        json={"title": "Nonblocking", "starts_at": START, "ends_at": END, "blocks_time": False},
    )
    assert nonblocking.status_code == 201
    create_task(client, deadline_at="2026-10-07T09:30:00Z")
    response = client.post(PATH, headers=headers, json=PAYLOAD)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["verified"]
    assert result["timezone"] == client.get("/api/v1/users/me").json()["timezone"]
    assert result["free"] == [
        {"starts_at": START, "ends_at": "2026-10-07T10:00:00Z"},
        {"starts_at": "2026-10-07T11:00:00Z", "ends_at": END},
    ]
    assert result["conflicts"] == [{"candidate_index": 0, "event_ids": [f"personal:{event['id']}"]}]
    assert response.headers["cache-control"] == "no-store"
    assert len(result["snapshot"]) == 64 and "description" not in result["events"][0]
    assert client.get(f"/api/v1/calendar/personal-events/{event['id']}").json() == event
    excluded = client.post(
        PATH, headers=headers, json=PAYLOAD | {"exclude_personal_event_id": event["id"]}
    )
    assert excluded.status_code == 200 and len(excluded.json()["free"]) == 1
    assert (
        client.post(
            PATH, headers=headers, json=PAYLOAD | {"exclude_personal_event_id": str(uuid4())}
        ).status_code
        == 404
    )
    assert client.post(PATH, json=PAYLOAD).status_code == 403
    client.cookies.clear()
    assert client.post(PATH, headers=headers, json=PAYLOAD).status_code == 401


def test_expected_official_schedule_never_implies_verified_coverage(enrolled: TestClient) -> None:
    response = enrolled.post(PATH, headers=csrf_headers(enrolled), json=PAYLOAD)
    assert response.status_code == 200, response.text
    assert not response.json()["verified"]
    assert "schedule_coverage_unknown" in response.json()["warnings"]


@pytest.mark.parametrize(
    "changes",
    [
        {"starts_at": 0},
        {"starts_at": "2026-10-07"},
        {"starts_at": "2026-10-07T09:00:00"},
        {"ends_at": START},
        {"minimum_minutes": True},
        {"minimum_minutes": "15"},
        {"minimum_minutes": 0},
        {"user_id": str(uuid4())},
        {"windows": [{"starts_at": "2026-10-07T08:00:00Z", "ends_at": END}]},
        {"candidates": [{"starts_at": START, "ends_at": "2026-10-07T13:00:00Z"}]},
    ],
)
def test_invalid_availability_queries_are_rejected(calendar_client: TestClient, changes) -> None:
    response = calendar_client.post(
        PATH, headers=csrf_headers(calendar_client), json=PAYLOAD | changes
    )
    assert response.status_code == 422, response.text
