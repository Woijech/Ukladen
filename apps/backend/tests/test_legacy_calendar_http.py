from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, create_autospec
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_auth_http import CSRF_COOKIE, csrf_headers
from test_auth_http import application as application
from test_auth_http import browser_settings as browser_settings
from test_auth_http import client as client
from test_auth_http import database as database
from test_auth_http import issued as issued
from test_auth_http import limiter as limiter
from test_auth_http import login_service as login_service
from test_auth_http import sessions as sessions
from test_auth_sessions import settings as settings

from app.modules.calendar.application.ports import PersonalCalendarEventRepository
from app.modules.calendar.application.service import PersonalEventService
from app.modules.calendar.domain.events import PersonalCalendarEvent
from app.modules.calendar.presentation.routes import get_events
from app.modules.users.application.ports import UserAuthentication

EVENTS = "/api/v1/calendar/events"
NOW = datetime(2026, 10, 12, 8, tzinfo=UTC)


@pytest.fixture
def repository() -> Mock:
    return create_autospec(PersonalCalendarEventRepository, instance=True)


@pytest.fixture
def users() -> Mock:
    users = create_autospec(UserAuthentication, instance=True)
    users.is_active.return_value = True
    return users


@pytest.fixture(autouse=True)
def events(
    application: FastAPI,
    repository,
    users,
    issued,
) -> PersonalEventService:
    service = PersonalEventService(repository, users)
    application.dependency_overrides[get_events] = lambda: service
    return service


def event_for(user_id, **changes: object) -> PersonalCalendarEvent:
    event = PersonalCalendarEvent(
        id=uuid4(),
        user_id=user_id,
        title="Study session",
        description="Prepare for the next class.",
        starts_at=NOW,
        ends_at=NOW + timedelta(hours=1),
        is_busy=True,
        created_at=NOW,
        updated_at=NOW,
    )
    return replace(event, **changes)


def test_round_trip_crud(
    client: TestClient,
    repository,
    users,
    issued,
) -> None:
    user_id = issued.session.user_id
    event = event_for(user_id)
    repository.create.side_effect = lambda owner, created: created
    repository.get.side_effect = lambda owner, event_id: event if owner == user_id else None
    repository.update.side_effect = lambda owner, updated: updated
    repository.delete.side_effect = lambda owner, event_id: owner == user_id

    headers = csrf_headers(client)
    payload = {
        "title": "Study session",
        "description": "Prepare for the next class.",
        "starts_at": NOW.isoformat(),
        "ends_at": (NOW + timedelta(hours=1)).isoformat(),
    }
    created = client.post(EVENTS, headers=headers, json=payload)
    assert created.status_code == 201
    body = created.json()
    assert created.headers["location"] == f"{EVENTS}/{body['id']}"
    assert body["title"] == "Study session" and body["is_busy"] is True
    assert set(body) == {
        "id",
        "title",
        "description",
        "starts_at",
        "ends_at",
        "is_busy",
        "created_at",
        "updated_at",
    }
    assert created.headers["cache-control"] == "no-store"

    read = client.get(f"{EVENTS}/{body['id']}")
    assert read.status_code == 200 and read.headers["cache-control"] == "no-store"
    read_body = read.json()
    assert read_body["starts_at"] == body["starts_at"]
    assert read_body["ends_at"] == body["ends_at"]
    assert read_body["title"] == body["title"]
    assert read_body["is_busy"] is True

    repository.list_for_period.return_value = [event]
    listing = client.get(
        EVENTS,
        params={"starts_at": NOW.isoformat(), "ends_at": (NOW + timedelta(days=1)).isoformat()},
    )
    assert listing.status_code == 200 and len(listing.json()) == 1
    repository.list_for_period.assert_called_with(user_id, NOW, NOW + timedelta(days=1))

    repository.get.side_effect = None
    repository.get.return_value = event
    patched = client.patch(
        f"{EVENTS}/{body['id']}",
        headers=headers,
        json={"title": "Renamed", "is_busy": False},
    )
    assert patched.status_code == 200 and patched.json()["title"] == "Renamed"
    assert patched.json()["description"] == "Prepare for the next class."
    assert patched.json()["is_busy"] is False

    deleted = client.delete(f"{EVENTS}/{body['id']}", headers=headers)
    assert deleted.status_code == 204 and not deleted.content


def test_period_query_and_body_validation(client: TestClient, issued) -> None:
    headers = csrf_headers(client)
    start = (NOW + timedelta(days=1)).isoformat()
    end = (NOW + timedelta(days=2)).isoformat()

    response = client.get(EVENTS, params={"starts_at": start, "ends_at": end})
    assert response.status_code == 200

    naive = client.get(EVENTS, params={"starts_at": "2026-10-13T08:00:00", "ends_at": end})
    assert naive.status_code == 422 and naive.json() == {"detail": "Invalid request."}

    reversed_period = client.get(EVENTS, params={"starts_at": end, "ends_at": start})
    assert reversed_period.status_code == 422

    too_long = client.get(
        EVENTS,
        params={
            "starts_at": NOW.isoformat(),
            "ends_at": (NOW + timedelta(days=400)).isoformat(),
        },
    )
    assert too_long.status_code == 422

    missing = client.get(EVENTS, params={"starts_at": start})
    assert missing.status_code == 422

    for payload in (
        {"title": "x" * 201, "starts_at": start, "ends_at": end},
        {"title": "Study session", "starts_at": start, "ends_at": start},
        {"title": "Study session", "starts_at": start, "ends_at": end, "unknown": 1},
        {"starts_at": start, "ends_at": end},
    ):
        assert client.post(EVENTS, headers=headers, json=payload).status_code == 422

    empty_patch = client.patch(f"{EVENTS}/{uuid4()}", headers=headers, json={})
    assert empty_patch.status_code == 422
    assert (
        client.patch(f"{EVENTS}/{uuid4()}", headers=headers, json={"title": None}).status_code
        == 422
    )


def test_missing_and_foreign_events_return_404(client: TestClient, repository, issued) -> None:
    user_id, other_id = issued.session.user_id, uuid4()
    event = event_for(user_id)
    repository.get.side_effect = lambda owner, event_id: (
        event if owner == user_id and event_id == event.id else None
    )
    repository.delete.return_value = False
    repository.update.return_value = None
    headers = csrf_headers(client)

    for method in ("get", "patch", "delete"):
        path = f"{EVENTS}/{other_id}"
        if method == "get":
            response = client.get(path)
        elif method == "patch":
            response = client.patch(path, headers=headers, json={"title": "Renamed"})
        else:
            response = client.delete(path, headers=headers)
        assert response.status_code == 404

    assert client.get(f"{EVENTS}/{event.id}").status_code == 200


def test_inactive_user_clears_session_cookie(
    client: TestClient,
    users,
    repository,
    issued,
) -> None:
    users.is_active.return_value = False
    client.cookies.set(CSRF_COOKIE, "x" * 43)
    headers = csrf_headers(client)
    response = client.post(
        EVENTS,
        headers=headers,
        json={
            "title": "Study session",
            "starts_at": NOW.isoformat(),
            "ends_at": (NOW + timedelta(hours=1)).isoformat(),
        },
    )
    assert response.status_code == 401
    assert "Max-Age=0" in response.headers["set-cookie"]
    repository.create.assert_not_called()


def test_mutations_require_csrf(client: TestClient) -> None:
    payload = {
        "title": "Study session",
        "starts_at": NOW.isoformat(),
        "ends_at": (NOW + timedelta(hours=1)).isoformat(),
    }
    assert client.post(EVENTS, json=payload).status_code == 403
    assert client.patch(f"{EVENTS}/{uuid4()}", json={"title": "Renamed"}).status_code == 403
    assert client.delete(f"{EVENTS}/{uuid4()}").status_code == 403


def test_openapi_contract(client: TestClient) -> None:
    schema = client.get("/api/openapi.json").json()
    assert set(schema["paths"][EVENTS]) == {"get", "post"}
    assert set(schema["paths"][f"{EVENTS}/{{event_id}}"]) == {"get", "patch", "delete"}
    assert schema["components"]["schemas"]["EventPatch"]["additionalProperties"] is False
