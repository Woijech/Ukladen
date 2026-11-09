import json
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_ai_http import ai_client as ai_client
from test_ai_http import browser_settings as browser_settings
from test_ai_http import calendar_client as calendar_client
from test_ai_http import concurrent_engine as concurrent_engine
from test_ai_http import create, submit
from test_ai_http import live_client as live_client
from test_ai_http import password_hash as password_hash
from test_ai_http import settings as settings
from test_auth_http import browser_login, csrf_headers, seed_user

from app.modules.ai.application.diagnostics import bounded_payload
from app.modules.ai.infrastructure.diagnostic_models import DiagnosticChatModel, DiagnosticRunModel
from app.modules.ai.infrastructure.diagnostics import purge_diagnostics

BASE = "/api/v1/ai/diagnostics"


def grant(client):
    app = cast(FastAPI, client.app)
    owner = UUID(client.get(BASE + "/access").json()["user_id"])
    app.state.settings = app.state.settings.model_copy(update={"ai_diagnostic_admin_ids": [owner]})
    return owner


def test_redacts_structured_and_embedded_credentials_and_reasoning_and_bounds_payload():
    payload = bounded_payload(
        {
            "key": "private",
            "body": '{"password":"secret","answer":"ok"}',
            "blocks": [{"type": "reasoning", "text": "hidden thoughts"}],
            "header": "Bearer privatebearertoken",
            "text": "sk-or-v1-privatesecret",
        }
    )
    raw = json.dumps(payload)
    assert all(value not in raw for value in ("private", "secret", "hidden thoughts"))
    assert payload["value"]["body"]["answer"] == "ok"
    assert bounded_payload("x" * 100000)["truncated"]
    assert len(json.dumps(bounded_payload("я" * 100000)).encode()) < 65536


def test_denied_by_default_csrf_and_cross_owner_reads(ai_client, concurrent_engine, password_hash):
    assert ai_client.get(BASE + "/access").json()["allowed"] is False
    assert ai_client.get(BASE + "/runs").status_code == 403
    assert (
        ai_client.post(BASE + "/conversations", json={"title": "QA", "demo": True}).status_code
        == 403
    )
    owner = grant(ai_client)
    assert (
        ai_client.post(BASE + "/conversations", json={"title": "QA", "demo": True}).status_code
        == 403
    )
    chat = ai_client.post(
        BASE + "/conversations", headers=csrf_headers(ai_client), json={"title": "QA", "demo": True}
    ).json()
    result = submit(ai_client, chat).json()
    assert result["status"] == "completed"
    seed_user(concurrent_engine, "diagnostic-other@example.com", password_hash)
    browser_login(ai_client, "diagnostic-other@example.com")
    other = UUID(ai_client.get(BASE + "/access").json()["user_id"])
    app = cast(FastAPI, ai_client.app)
    app.state.settings = app.state.settings.model_copy(
        update={"ai_diagnostic_admin_ids": [owner, other]}
    )
    assert ai_client.get(BASE + "/runs").json()["items"] == []
    assert ai_client.get(BASE + f"/runs/{result['id']}").status_code == 404
    assert (
        ai_client.put(
            BASE + f"/runs/{result['id']}/review",
            headers=csrf_headers(ai_client),
            json={"verdict": "passed"},
        ).status_code
        == 404
    )


def test_stream_capture_replay_review_delete_and_conversation_cascade(ai_client, concurrent_engine):
    owner = grant(ai_client)
    ordinary = create(ai_client)
    plain = submit(ai_client, ordinary).json()
    assert ai_client.get(BASE + f"/runs/{plain['id']}").json()["trace"]["captured"] is False
    chat_response = ai_client.post(
        BASE + "/conversations", headers=csrf_headers(ai_client), json={"title": "QA", "demo": True}
    )
    assert chat_response.status_code == 201, chat_response.text
    chat = chat_response.json()
    from uuid import uuid4

    payload = {"message": "Synthetic request", "submission_id": str(uuid4())}
    path = f"/api/v1/ai/conversations/{chat['id']}/messages/stream"
    response = ai_client.post(path, headers=csrf_headers(ai_client), json=payload)
    assert "event: done" in response.text
    items = ai_client.get(BASE + "/runs?limit=1").json()
    assert items["has_more"]
    run_id = items["items"][0]["id"]
    detail = ai_client.get(BASE + f"/runs/{run_id}").json()
    assert detail["run"]["status"] == "completed"
    trace = detail["trace"]
    kinds = [event["kind"] for event in trace["events"]]
    assert kinds == [
        "model_input",
        "model_request",
        "model_usage",
        "model_response",
        "tool_request",
        "tool_response",
        "model_input",
        "model_request",
        "model_usage",
        "model_response",
    ]
    assert "fake_double" in json.dumps(trace)
    ai_client.post(path, headers=csrf_headers(ai_client), json=payload)
    assert ai_client.get(BASE + f"/runs/{run_id}").json()["trace"] == trace
    review = BASE + f"/runs/{run_id}/review"
    assert ai_client.put(review, json={"verdict": "passed"}).status_code == 403
    assert (
        ai_client.put(
            review,
            headers=csrf_headers(ai_client),
            json={"verdict": "passed", "note": "Observed 14"},
        ).status_code
        == 204
    )
    assert ai_client.get(BASE + f"/runs/{run_id}").json()["trace"]["note"] == "Observed 14"
    assert ai_client.get(BASE + "/runs?status=failed").json()["items"] == []
    assert ai_client.get(BASE + "/runs?days=31").status_code == 422
    with Session(concurrent_engine) as database:
        row = database.get(DiagnosticRunModel, UUID(run_id))
        assert row and row.user_id == owner
    assert (
        ai_client.delete(
            f"/api/v1/ai/conversations/{chat['id']}", headers=csrf_headers(ai_client)
        ).status_code
        == 204
    )
    with Session(concurrent_engine) as database:
        assert database.get(DiagnosticRunModel, UUID(run_id)) is None
        assert database.get(DiagnosticChatModel, UUID(chat["id"])) is None
    assert ai_client.get(BASE + f"/runs/{run_id}").json()["trace"]["captured"] is False


def test_capture_retention_and_explicit_clear(ai_client, concurrent_engine):
    grant(ai_client)
    chat = ai_client.post(
        BASE + "/conversations", headers=csrf_headers(ai_client), json={"title": "QA", "demo": True}
    ).json()
    result = submit(ai_client, chat).json()
    path = BASE + f"/runs/{result['id']}"
    assert ai_client.delete(path + "/capture", headers=csrf_headers(ai_client)).status_code == 204
    assert ai_client.get(path).json()["trace"]["captured"] is False
    result = submit(ai_client, chat).json()
    with Session(concurrent_engine) as database, database.begin():
        row = database.get(DiagnosticRunModel, UUID(result["id"]))
        assert row
        row.created_at = datetime.now(UTC) - timedelta(days=8)
        row.verdict = "passed"
    assert ai_client.get(BASE + f"/runs/{result['id']}").json()["trace"]["captured"] is False
    expired = next(
        item for item in ai_client.get(BASE + "/runs").json()["items"] if item["id"] == result["id"]
    )
    assert expired["verdict"] == "unreviewed" and expired["captured"] is False
    sessions = cast(FastAPI, ai_client.app).state.session_factory
    purge_diagnostics(sessions, datetime.now(UTC))
    with Session(concurrent_engine) as database:
        assert not list(database.scalars(select(DiagnosticRunModel)))


def test_capture_storage_is_bounded_and_revoked_operator_stops_future_capture(
    ai_client, concurrent_engine
):
    from app.modules.ai.application.diagnostics import record
    from app.modules.ai.infrastructure.diagnostics import SqlAlchemyDiagnostics
    from app.modules.ai.infrastructure.orm import RunModel
    from app.modules.ai.infrastructure.repository import run_entity

    grant(ai_client)
    chat = ai_client.post(
        BASE + "/conversations", headers=csrf_headers(ai_client), json={"title": "QA", "demo": True}
    ).json()
    result = submit(ai_client, chat).json()
    with Session(concurrent_engine) as database, database.begin():
        row = database.get(RunModel, UUID(result["id"]))
        assert row
        row.status, row.finished_at = "running", None
        run = run_entity(row)
    sessions = cast(FastAPI, ai_client.app).state.session_factory
    store = SqlAlchemyDiagnostics(sessions)
    with store.capturing(run, True):
        for number in range(100):
            record("tool_response", {"number": number, "content": "x" * 10000})
    trace = store.read(run.user_id, run.id)
    assert trace["truncated"] and len(trace["events"]) <= 64
    assert len(json.dumps(trace["events"]).encode()) <= 262144
    with store.capturing(run, False):
        record("tool_response", {"content": "must not be captured"})
    assert "must not be captured" not in json.dumps(store.read(run.user_id, run.id))
    assert (
        ai_client.delete(
            BASE + f"/runs/{run.id}/capture", headers=csrf_headers(ai_client)
        ).status_code
        == 409
    )


def test_diagnostic_migration_refuses_to_discard_retained_capture(ai_client, concurrent_engine):
    from test_auth_persistence import migration_config

    from alembic import command

    grant(ai_client)
    chat = ai_client.post(
        BASE + "/conversations", headers=csrf_headers(ai_client), json={"title": "QA", "demo": True}
    ).json()
    run = submit(ai_client, chat).json()
    with concurrent_engine.connect() as connection, connection.begin():
        with pytest.raises(RuntimeError, match="Clear retained diagnostics"):
            command.downgrade(migration_config(connection), "0040_ai_review_delivery")
    assert ai_client.get(BASE + f"/runs/{run['id']}").json()["trace"]["captured"]
