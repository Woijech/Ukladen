from fastapi.testclient import TestClient
from sqlalchemy import Engine
from test_ai_http import ai_client as ai_client
from test_ai_http import browser_settings as browser_settings
from test_ai_http import calendar_client as calendar_client
from test_ai_http import concurrent_engine as concurrent_engine
from test_ai_http import live_client as live_client
from test_ai_http import password_hash as password_hash
from test_ai_http import settings as settings
from test_auth_http import browser_login, csrf_headers, seed_user


def test_settings_are_disabled_private_versioned_and_csrf_protected(
    ai_client: TestClient, concurrent_engine: Engine, password_hash: str
):
    path = "/api/v1/ai/reviews/settings"
    original = ai_client.get(path)
    assert original.status_code == 200, original.text
    assert original.headers["cache-control"] == "no-store"
    assert original.json()["version"] == 0
    assert original.json()["configuration"]["enabled"] is False
    payload = {"configuration": {"daily_time": "10:15"}, "expected_version": 0}
    assert ai_client.put(path, json=payload).status_code == 403
    saved = ai_client.put(path, headers=csrf_headers(ai_client), json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["version"] == 1
    assert saved.json()["configuration"]["daily_time"] == "10:15"
    assert ai_client.put(path, headers=csrf_headers(ai_client), json=payload).status_code == 409
    payload["expected_version"] = 1
    payload["configuration"] = {"enabled": True}
    assert ai_client.put(path, headers=csrf_headers(ai_client), json=payload).status_code == 422
    seed_user(concurrent_engine, "reviews-other@example.com", password_hash)
    browser_login(ai_client, "reviews-other@example.com")
    assert ai_client.get(path).json()["version"] == 0
    ai_client.cookies.clear()
    assert ai_client.get(path).status_code == 401


def test_settings_storage_failure_is_unavailable(ai_client: TestClient):
    from unittest.mock import patch

    from sqlalchemy.exc import SQLAlchemyError

    from app.modules.ai.infrastructure.review_settings import SqlAlchemyReviewSettings

    with patch.object(SqlAlchemyReviewSettings, "get", side_effect=SQLAlchemyError("private")):
        response = ai_client.get("/api/v1/ai/reviews/settings")
    assert response.status_code == 503
    assert "private" not in response.text


def test_collection_reuses_owned_services_and_respects_scope(ai_client: TestClient, monkeypatch):
    from datetime import UTC, datetime, timedelta
    from typing import cast
    from uuid import UUID

    from fastapi import FastAPI

    from app.modules.ai.application.reviews import ReviewConfiguration
    from app.modules.ai.application.source_queries import SourceScope
    from app.modules.ai.infrastructure.review_collection import collect_review
    from app.modules.ai.infrastructure.sources import SqlAlchemySourceReader
    from app.modules.tasks.infrastructure.orm import TaskModel

    headers = csrf_headers(ai_client)
    first = ai_client.post("/api/v1/tasks", headers=headers, json={"title": "Calculus"}).json()
    second = ai_client.post("/api/v1/tasks", headers=headers, json={"title": "Physics"}).json()
    page = ai_client.post(
        "/api/v1/notes/pages",
        headers=headers,
        json={"title": "Calculus", "content": "Useful derivatives"},
    ).json()
    application = cast(FastAPI, ai_client.app)
    reader = SqlAlchemySourceReader(
        application.state.session_factory, application.state.academic_provider, 3600
    )
    with application.state.session_factory() as database, database.begin():
        row = database.get(TaskModel, UUID(first["id"]))
        assert row is not None
        user_id = row.user_id
        now = datetime.now(UTC)
        reader.service(database).calendar.calendar.create_personal_event(
            user_id,
            {
                "title": "Nonblocking event",
                "starts_at": now + timedelta(hours=1),
                "ends_at": now + timedelta(hours=2),
                "blocks_time": False,
            },
        )
        result = collect_review(database, reader, user_id, ReviewConfiguration(), datetime.now(UTC))
        assert {item["id"] for item in result.data["tasks"]} == {first["id"], second["id"]}
        assert any(source.id == page["id"] for source in result.sources)
        assert any(event["title"] == "Nonblocking event" for event in result.data["events"])
        assert not any(issue["kind"] == "conflict" for issue in result.issues)
    from app.modules.tasks.infrastructure.repository import SqlAlchemyTaskRepository

    def unexpected_hierarchy_read(*args):
        raise AssertionError("Explicit scope must not inspect unselected descendants")

    monkeypatch.setattr(SqlAlchemyTaskRepository, "has_open_descendants", unexpected_hierarchy_read)
    with application.state.session_factory() as database, database.begin():
        result = collect_review(
            database,
            reader,
            user_id,
            ReviewConfiguration(source_scope=SourceScope(task_ids=(UUID(first["id"]),))),
            datetime.now(UTC),
        )
        assert [item["id"] for item in result.data["tasks"]] == [first["id"]]
        assert result.data["related_materials"] == [] and result.data["events"] == []
        assert all(source.source == "task" for source in result.sources)

    outside = ai_client.post("/api/v1/tasks", headers=headers, json={"title": "Outside"}).json()
    with application.state.session_factory() as database, database.begin():
        row = database.get(TaskModel, UUID(first["id"]))
        assert row is not None
        row.parent_id = UUID(outside["id"])
        database.flush()
        result = collect_review(
            database,
            reader,
            user_id,
            ReviewConfiguration(
                source_scope=SourceScope(
                    task_ids=(UUID(first["id"]), UUID(second["id"])),
                    calendar=True,
                )
            ),
            datetime.now(UTC),
        )
        assert "scope_hierarchy_uncertain" in result.warnings
        assert not any(issue["kind"] == "overload" for issue in result.issues)
        assert outside["id"] not in {item["id"] for item in result.data["tasks"]}
