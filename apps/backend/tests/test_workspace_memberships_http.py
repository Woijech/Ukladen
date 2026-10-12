from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from test_auth_http import browser_login, csrf_headers, seed_user
from test_calendar_http import create_event
from test_calendar_http import enrolled as enrolled
from test_calendar_http import store as store
from test_logging import capture_json, entries
from test_notes_http import BASE as NOTES
from test_notes_http import change, create_page, lifecycle
from test_schedule_expansion import schedule_fixture
from test_workspace_http import BASE, create_organization
from test_workspace_http import browser_settings as browser_settings
from test_workspace_http import calendar_client as calendar_client
from test_workspace_http import concurrent_engine as concurrent_engine
from test_workspace_http import live_client as live_client
from test_workspace_http import password_hash as password_hash
from test_workspace_http import settings as settings

from app.modules.academics.infrastructure.orm import AcademicProfileModel
from app.modules.calendar.infrastructure.orm import PersonalCalendarEventModel
from app.modules.schedule.application.expansion import expand_schedule
from app.modules.schedule.infrastructure.orm import OfficialScheduleEventModel
from app.modules.schedule.infrastructure.storage import SqlAlchemyScheduleStore
from app.modules.workspace.domain.membership import Membership
from app.modules.workspace.infrastructure.orm import OrganizationModel
from app.modules.workspace.infrastructure.repository import SqlAlchemyMemberships


def members(organization: dict, kind: str = "collections") -> str:
    return f"{BASE}/{kind}/{organization['id']}/members"


def put(client: TestClient, path: str, target_type: str, target_id: str) -> dict:
    response = client.put(f"{path}/{target_type}/{target_id}", headers=csrf_headers(client))
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("kind", ["collections", "tags"])
def test_membership_lists_reverse_lookups_and_safe_deletion(
    calendar_client: TestClient, kind: str
) -> None:
    first, second = (create_organization(calendar_client, kind) for _ in range(2))
    page = create_page(calendar_client, content="private-member-document")
    child = create_page(calendar_client, parent_id=page["id"])
    event = create_event(calendar_client)
    assert (
        calendar_client.put(
            f"/api/v1/relations/calendar-events/personal/{event['id']}/pages/{page['id']}",
            headers=csrf_headers(calendar_client),
        ).status_code
        == 200
    )
    path = members(first, kind)
    with capture_json() as output:
        member = put(calendar_client, path, "page", page["id"])
        assert put(calendar_client, path, "page", page["id"]) == member
        put(calendar_client, path, "personal", event["id"])
        put(calendar_client, members(second, kind), "page", page["id"])
        put(calendar_client, members(second, kind), "personal", event["id"])
        response = calendar_client.get(path)
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        assert len(response.json()["items"]) == 2
        assert "user_id" not in member
        for item in response.json()["items"]:
            assert "document" not in item["target"] and "content" not in item["target"]
        for target_type, count in (("page", 1), ("personal", 1), ("official", 0), ("event", 1)):
            assert (
                len(calendar_client.get(f"{path}?target_type={target_type}").json()["items"])
                == count
            )
        assert (
            calendar_client.get(path + "?limit=1&offset=1").json()["items"][0]["membership"][
                "target_type"
            ]
            == "personal"
        )
        assert calendar_client.get(f"{BASE}/pages/{child['id']}/{kind}").json()["items"] == []
        for reverse in (
            f"{BASE}/pages/{page['id']}/{kind}",
            f"{BASE}/calendar-events/personal/{event['id']}/{kind}",
        ):
            assert {item["id"] for item in calendar_client.get(reverse).json()["items"]} == {
                first["id"],
                second["id"],
            }
            assert calendar_client.get(reverse + "?offset=2").json()["items"] == []
        changed_page = change(calendar_client, page, title="Changed page").json()
        event_path = f"/api/v1/calendar/personal-events/{event['id']}"
        changed_event = calendar_client.patch(
            event_path,
            headers=csrf_headers(calendar_client),
            json={"expected_version": 1, "title": "Changed event"},
        ).json()
        assert [item["target"]["title"] for item in calendar_client.get(path).json()["items"]] == [
            "Changed page",
            "Changed event",
        ]
        assert calendar_client.get(f"{BASE}/{kind}/{first['id']}").json()["version"] == 1
        assert (
            calendar_client.delete(
                f"{BASE}/{kind}/{first['id']}?expected_version=1",
                headers=csrf_headers(calendar_client),
            ).status_code
            == 204
        )
        assert calendar_client.get(path).status_code == 404
        assert len(calendar_client.get(members(second, kind)).json()["items"]) == 2
        assert calendar_client.get(f"{NOTES}/{page['id']}").json() == changed_page
        assert calendar_client.get(event_path).json() == changed_event
    assert (
        "private-member-document" not in output.getvalue() and page["id"] not in output.getvalue()
    )
    assert any(row["event"] == "workspace.member_added" for row in entries(output))


def test_trash_and_personal_deletion_preserve_unrelated_objects(
    calendar_client: TestClient,
) -> None:
    organization = create_organization(calendar_client)
    path = members(organization)
    page, event = create_page(calendar_client), create_event(calendar_client)
    put(calendar_client, path, "page", page["id"])
    put(calendar_client, path, "personal", event["id"])
    trashed = lifecycle(calendar_client, page, "trash")
    assert trashed.status_code == 200
    assert calendar_client.get(path).json()["items"][0]["target"]["trashed_at"] is not None
    assert calendar_client.get(f"{BASE}/pages/{page['id']}/collections").json()["items"] == [
        organization
    ]
    assert (
        calendar_client.put(
            f"{path}/page/{page['id']}", headers=csrf_headers(calendar_client)
        ).status_code
        == 409
    )
    for _ in range(2):
        assert (
            calendar_client.delete(
                f"{path}/page/{page['id']}", headers=csrf_headers(calendar_client)
            ).status_code
            == 204
        )
    assert lifecycle(calendar_client, trashed.json(), "restore").status_code == 200
    assert (
        calendar_client.delete(
            f"/api/v1/calendar/personal-events/{event['id']}", headers=csrf_headers(calendar_client)
        ).status_code
        == 204
    )
    assert calendar_client.get(path).json()["items"] == []
    assert calendar_client.get(f"{NOTES}/{page['id']}").status_code == 200


def test_member_target_and_container_ownership_sessions_and_validation(
    calendar_client: TestClient, concurrent_engine: Engine, password_hash: str
) -> None:
    organization = create_organization(calendar_client)
    page, event = create_page(calendar_client), create_event(calendar_client)
    path = members(organization)
    put(calendar_client, path, "page", page["id"])
    for method in ("PUT", "DELETE"):
        assert calendar_client.request(method, f"{path}/page/{page['id']}").status_code == 403
    assert (
        calendar_client.put(
            f"{path}/event/{event['id']}", headers=csrf_headers(calendar_client)
        ).status_code
        == 422
    )
    assert calendar_client.get(path + "?target_type=unknown").status_code == 422
    assert calendar_client.get(members(organization, "tags")).status_code == 404
    for query in ("limit=0", "limit=201", "offset=-1", "offset=2147483648"):
        for route in (
            path,
            f"{BASE}/pages/{page['id']}/collections",
            f"{BASE}/calendar-events/personal/{event['id']}/tags",
        ):
            assert calendar_client.get(f"{route}?{query}").status_code == 422
    seed_user(concurrent_engine, "other@example.com", password_hash)
    browser_login(calendar_client, "other@example.com")
    owned = create_organization(calendar_client)
    owned_page = create_page(calendar_client)
    for container, target_type, target_id in (
        (organization, "page", owned_page["id"]),
        (owned, "page", page["id"]),
        (owned, "personal", event["id"]),
    ):
        assert (
            calendar_client.put(
                f"{members(container)}/{target_type}/{target_id}",
                headers=csrf_headers(calendar_client),
            ).status_code
            == 404
        )
    assert calendar_client.get(path).status_code == 404
    assert (
        calendar_client.delete(
            f"{path}/page/{page['id']}", headers=csrf_headers(calendar_client)
        ).status_code
        == 404
    )
    reverse_page = f"{BASE}/pages/{page['id']}/collections"
    reverse_event = f"{BASE}/calendar-events/personal/{event['id']}/tags"
    assert calendar_client.get(reverse_page).status_code == 404
    assert calendar_client.get(reverse_event).status_code == 404
    assert calendar_client.get(members(owned)).json()["items"] == []
    calendar_client.cookies.clear()
    for route in (path, reverse_page, reverse_event):
        assert calendar_client.get(route).status_code == 401


def test_official_members_survive_refresh_overrides_profile_changes_and_withdrawal(
    enrolled: TestClient, store: SqlAlchemyScheduleStore, concurrent_engine: Engine
) -> None:
    snapshot, now = schedule_fixture(), datetime.now(UTC)
    lesson = replace(expand_schedule(snapshot)[0], subgroup=1)
    other = replace(lesson, id=uuid4(), subgroup=2)
    token = store.claim(24066, "353501", now)
    assert token and store.apply(24066, token, snapshot, [lesson, other], now)
    organization = create_organization(enrolled)
    path = members(organization)
    put(enrolled, path, "official", str(lesson.id))
    assert (
        enrolled.put(f"{path}/official/{other.id}", headers=csrf_headers(enrolled)).status_code
        == 404
    )
    assert (
        enrolled.put(
            f"/api/v1/calendar/overrides/{lesson.id}",
            headers=csrf_headers(enrolled),
            json={
                "title": "My lecture",
                "hidden": True,
                "skipped": True,
                "starts_at": "2026-09-14T18:00:00+03:00",
                "ends_at": "2026-09-14T19:00:00+03:00",
            },
        ).status_code
        == 200
    )
    reference = enrolled.get(path).json()["items"][0]["target"]
    assert reference["title"] == "My lecture" and reference["hidden"] and reference["skipped"]
    assert reference["starts_at"] == "2026-09-14T15:00:00Z"
    now += timedelta(hours=2)
    token = store.claim(24066, "353501", now)
    assert token and store.apply(
        24066, token, snapshot, [replace(lesson, id=uuid4(), rooms=("new",))], now
    )
    assert enrolled.get(path).json()["items"][0]["membership"]["target_id"] == str(lesson.id)
    with Session(concurrent_engine) as database, database.begin():
        database.query(AcademicProfileModel).one().subgroup = 2
    assert enrolled.get(path).json()["items"][0]["target"]["source_status"] == "outside_profile"
    assert (
        enrolled.put(f"{path}/official/{lesson.id}", headers=csrf_headers(enrolled)).status_code
        == 404
    )
    reverse = f"{BASE}/calendar-events/official/{lesson.id}/collections"
    assert enrolled.get(reverse).json()["items"] == [organization]
    assert enrolled.get(reverse + "?offset=1").json()["items"] == []
    assert enrolled.get(f"{BASE}/calendar-events/official/{lesson.id}/tags").json()["items"] == []
    now += timedelta(hours=2)
    token = store.claim(24066, "353501", now)
    assert token and store.apply(24066, token, None, [], now)
    assert enrolled.get(path).json()["items"][0]["target"]["source_status"] == "inactive_source"
    with Session(concurrent_engine) as database, database.begin():
        with pytest.raises(IntegrityError), database.begin_nested():
            database.execute(
                delete(OfficialScheduleEventModel).where(OfficialScheduleEventModel.id == lesson.id)
            )
        database.query(AcademicProfileModel).one().subgroup = 1
    empty = create_organization(enrolled)
    assert (
        enrolled.put(
            f"{members(empty)}/official/{lesson.id}", headers=csrf_headers(enrolled)
        ).status_code
        == 409
    )
    assert (
        enrolled.delete(f"{path}/official/{lesson.id}", headers=csrf_headers(enrolled)).status_code
        == 204
    )
    assert enrolled.get(path).json()["items"] == []
    assert enrolled.get(reverse).status_code == 409


def test_failed_member_insert_rolls_back_without_success_log(calendar_client: TestClient) -> None:
    organization, page = create_organization(calendar_client), create_page(calendar_client)
    original = SqlAlchemyMemberships.put

    def fail(self, value):
        original(self, value)
        raise SQLAlchemyError("private-membership-sql")

    with patch.object(SqlAlchemyMemberships, "put", fail), capture_json() as output:
        response = calendar_client.put(
            f"{members(organization)}/page/{page['id']}", headers=csrf_headers(calendar_client)
        )
    assert response.status_code == 503 and "private" not in response.text
    assert "private-membership-sql" not in output.getvalue()
    assert not any(row["event"] == "workspace.member_added" for row in entries(output))
    assert calendar_client.get(members(organization)).json()["items"] == []
    assert calendar_client.get(f"{NOTES}/{page['id']}").json() == page


def test_duplicate_members_are_safe_under_concurrent_inserts(
    calendar_client: TestClient, concurrent_engine: Engine
) -> None:
    organization, page = create_organization(calendar_client), create_page(calendar_client)
    with Session(concurrent_engine) as database:
        row = database.get(OrganizationModel, UUID(organization["id"]))
        assert row
        owner = row.user_id

    def insert_member() -> UUID:
        with Session(concurrent_engine) as database, database.begin():
            return (
                SqlAlchemyMemberships(database)
                .put(
                    Membership(
                        uuid4(),
                        owner,
                        UUID(organization["id"]),
                        "page",
                        UUID(page["id"]),
                        datetime.now(UTC),
                    )
                )
                .id
            )

    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(insert_member), pool.submit(insert_member)]
        assert futures[0].result() == futures[1].result()
    assert len(calendar_client.get(members(organization)).json()["items"]) == 1


def test_member_resolution_uses_one_snapshot_during_target_deletion(
    calendar_client: TestClient, concurrent_engine: Engine
) -> None:
    organization, event = create_organization(calendar_client), create_event(calendar_client)
    put(calendar_client, members(organization), "personal", event["id"])
    original = SqlAlchemyMemberships.list

    def delete_after_read(self, *args):
        result = original(self, *args)
        with Session(concurrent_engine) as database, database.begin():
            database.execute(
                delete(PersonalCalendarEventModel).where(
                    PersonalCalendarEventModel.id == UUID(event["id"])
                )
            )
        return result

    with patch.object(SqlAlchemyMemberships, "list", delete_after_read):
        response = calendar_client.get(members(organization))
    assert response.status_code == 200
    assert response.json()["items"][0]["target"]["title"] == event["title"]
    assert calendar_client.get(members(organization)).json()["items"] == []
