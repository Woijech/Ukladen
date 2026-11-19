from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from test_auth_http import browser_login, csrf_headers, seed_user
from test_auth_persistence import migration_config
from test_calendar_http import browser_settings as browser_settings
from test_calendar_http import calendar_client as calendar_client
from test_calendar_http import concurrent_engine as concurrent_engine
from test_calendar_http import live_client as live_client
from test_calendar_http import password_hash as password_hash
from test_calendar_http import settings as settings

from alembic import command

BASE = "/api/v1/calendar"
EVENT = {
    "title": "Workout",
    "starts_at": "2026-10-07T10:00:00+03:00",
    "ends_at": "2026-10-07T11:00:00+03:00",
}


def create_calendar(client: TestClient, name="Work") -> dict:
    response = client.post(
        BASE + "/calendars", headers=csrf_headers(client), json={"name": name, "color": "#70558e"}
    )
    assert response.status_code == 201, response.text
    assert "user_id" not in response.json()
    return response.json()


def test_calendar_crud_assignment_visibility_and_safe_delete(calendar_client: TestClient) -> None:
    client = calendar_client
    calendar = create_calendar(client)
    response = client.post(
        BASE + "/personal-events",
        headers=csrf_headers(client),
        json=EVENT | {"calendar_id": calendar["id"]},
    )
    assert response.status_code == 201, response.text
    event = response.json()
    assert event["calendar_id"] == calendar["id"]
    saved = client.patch(
        BASE + "/calendars/" + calendar["id"],
        headers=csrf_headers(client),
        json={"name": "Training", "color": "#aabbcc", "expected_version": 1},
    )
    assert saved.status_code == 200 and saved.json()["version"] == 2
    hidden = client.put(
        BASE + "/visibility",
        headers=csrf_headers(client),
        json={
            "version": 0,
            "default_visible": False,
            "hidden_calendar_ids": [calendar["id"]],
            "hidden_lesson_types": ["ЛК", "other"],
        },
    )
    assert hidden.status_code == 200 and hidden.json()["version"] == 1
    assert client.get(BASE + "/visibility").json() == hidden.json()
    assert (
        client.put(
            BASE + "/visibility", headers=csrf_headers(client), json=hidden.json() | {"version": 0}
        ).status_code
        == 409
    )
    resolved = client.get(BASE + "/events?date_from=2026-10-07&date_to=2026-10-07")
    assert resolved.status_code == 200
    assert resolved.json()["events"][0]["calendar_id"] == calendar["id"]
    assert resolved.json()["events"][0]["blocks_time"] is True
    assert (
        client.request(
            "DELETE",
            BASE + "/calendars/" + calendar["id"],
            headers=csrf_headers(client),
            json={"expected_version": 1},
        ).status_code
        == 409
    )
    assert (
        client.request(
            "DELETE",
            BASE + "/calendars/" + calendar["id"],
            headers=csrf_headers(client),
            json={"expected_version": 2},
        ).status_code
        == 204
    )
    retained = client.get(BASE + "/personal-events/" + event["id"]).json()
    assert retained["calendar_id"] is None and retained["version"] == event["version"] + 1
    assert retained["starts_at"] == event["starts_at"]
    assert client.get(BASE + "/visibility").json()["hidden_calendar_ids"] == []
    assert client.get(BASE + "/calendars").json()["items"] == []


def test_calendar_ownership_csrf_and_database_owner_constraint(
    calendar_client: TestClient, concurrent_engine: Engine, password_hash: str
) -> None:
    client = calendar_client
    calendar = create_calendar(client)
    assert (
        client.post(BASE + "/calendars", json={"name": "Bad", "color": "#ffffff"}).status_code
        == 403
    )
    seed_user(concurrent_engine, "calendar-other@example.com", password_hash)
    browser_login(client, "calendar-other@example.com")
    assert client.get(BASE + "/calendars").json()["items"] == []
    assert (
        client.post(
            BASE + "/personal-events",
            headers=csrf_headers(client),
            json=EVENT | {"calendar_id": calendar["id"]},
        ).status_code
        == 404
    )
    assert (
        client.patch(
            BASE + "/calendars/" + calendar["id"],
            headers=csrf_headers(client),
            json={"name": "Stolen", "color": "#ffffff", "expected_version": 1},
        ).status_code
        == 404
    )
    assert (
        client.put(
            BASE + "/visibility",
            headers=csrf_headers(client),
            json={
                "version": 0,
                "default_visible": True,
                "hidden_calendar_ids": [calendar["id"]],
                "hidden_lesson_types": [],
            },
        ).status_code
        == 404
    )
    own = client.post(BASE + "/personal-events", headers=csrf_headers(client), json=EVENT).json()
    with pytest.raises(IntegrityError), concurrent_engine.begin() as db:
        db.execute(
            text("UPDATE personal_calendar_events SET calendar_id = :calendar WHERE id = :event"),
            {"calendar": UUID(calendar["id"]), "event": UUID(own["id"])},
        )
    assert (
        client.put(
            BASE + "/visibility",
            headers=csrf_headers(client),
            json={
                "version": 0,
                "default_visible": True,
                "hidden_calendar_ids": [],
                "hidden_lesson_types": ["made-up"],
            },
        ).status_code
        == 422
    )


def test_calendar_migration_refuses_retained_data(
    calendar_client: TestClient, concurrent_engine: Engine
) -> None:
    create_calendar(calendar_client)
    with concurrent_engine.begin() as connection:
        with pytest.raises(RuntimeError, match="Retained calendar data"):
            command.downgrade(migration_config(connection), "0042_minsk_timezone")
