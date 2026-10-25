import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from typing import cast
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from test_ai_http import ai_client as ai_client
from test_ai_http import browser_settings as browser_settings
from test_ai_http import calendar_client as calendar_client
from test_ai_http import concurrent_engine as concurrent_engine
from test_ai_http import create
from test_ai_http import live_client as live_client
from test_ai_http import password_hash as password_hash
from test_ai_http import settings as settings
from test_auth_http import browser_login, csrf_headers, seed_user

from app.integrations.llm.fake import FakeChatModel
from app.modules.ai.application.lifecycle import AiService
from app.modules.ai.domain.state import Message
from app.modules.ai.infrastructure.lifecycle import PostgresAgentRunners, SqlAlchemyAiTransactions
from app.modules.ai.infrastructure.orm import ConversationModel, ProviderAttemptModel, RunModel
from app.modules.ai.infrastructure.repository import SqlAlchemyAiRepository
from app.modules.ai.presentation.routes import get_ai


def test_stream_replay_recovery_preferences_and_owner_isolation(
    ai_client: TestClient,
    concurrent_engine: Engine,
    password_hash: str,
) -> None:
    base = "/api/v1/ai"
    preferences = ai_client.get(base + "/preferences")
    assert preferences.json() == {"instructions": "", "version": 0}
    assert (
        ai_client.put(
            base + "/preferences", json={"instructions": "Brief", "expected_version": 0}
        ).status_code
        == 403
    )
    saved = ai_client.put(
        base + "/preferences",
        headers=csrf_headers(ai_client),
        json={"instructions": "Brief", "expected_version": 0},
    )
    assert saved.json() == {"instructions": "Brief", "version": 1}
    assert (
        ai_client.put(
            base + "/preferences",
            headers=csrf_headers(ai_client),
            json={"instructions": "stale", "expected_version": 0},
        ).status_code
        == 409
    )
    conversation = create(ai_client)
    path = f"{base}/conversations/{conversation['id']}"
    payload = {"message": "Hello", "submission_id": str(uuid4())}
    stream = ai_client.post(
        path + "/messages/stream", headers=csrf_headers(ai_client), json=payload
    )
    assert stream.status_code == 200, stream.text
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert stream.headers["cache-control"] == "no-store, no-transform"
    assert "event: delta" in stream.text and "event: done" in stream.text, stream.text
    assert "fake_double" in stream.text
    state = ai_client.get(path + "/state").json()
    assert state["run"]["status"] == "completed"
    assert "content" not in json.dumps(state["run"])
    repeated = ai_client.post(
        path + "/messages/stream", headers=csrf_headers(ai_client), json=payload
    )
    assert "event: delta" not in repeated.text
    assert len(ai_client.get(path + "/messages").json()["items"]) == 2
    assert ai_client.delete(path, headers=csrf_headers(ai_client)).status_code == 204
    assert ai_client.get(base + "/preferences").json()["instructions"] == "Brief"
    seed_user(concurrent_engine, "other@example.com", password_hash)
    browser_login(ai_client, "other@example.com")
    assert ai_client.get(base + "/preferences").json() == {"instructions": "", "version": 0}
    assert ai_client.get(path + "/state").status_code == 404
    assert (
        ai_client.post(
            path + "/messages/stream", headers=csrf_headers(ai_client), json=payload
        ).status_code
        == 404
    )


def test_usage_uses_owned_retained_attempts_and_historical_prices(
    ai_client: TestClient,
    concurrent_engine: Engine,
    password_hash: str,
) -> None:
    from uuid import UUID

    from test_ai_http import submit

    conversation = create(ai_client)
    run = submit(ai_client, conversation).json()
    assert ai_client.get("/api/v1/ai/usage").json()["fake"]["attempts"] == 2
    with Session(concurrent_engine) as database, database.begin():
        stored = database.get(RunModel, UUID(run["id"]))
        assert stored is not None
        stored.provider = "openrouter"
        stored.price = {
            "date": "2026-10-24",
            "currency": "USD",
            "input_per_million": "1",
            "output_per_million": "2",
        }
        attempts = list(
            database.scalars(
                select(ProviderAttemptModel)
                .where(ProviderAttemptModel.run_id == stored.id)
                .order_by(ProviderAttemptModel.number)
            )
        )
        attempts[0].input_tokens, attempts[0].output_tokens = 100, 50
        attempts[1].input_tokens, attempts[1].output_tokens = None, 0
    report = ai_client.get("/api/v1/ai/usage?days=30&limit=1").json()
    assert report["summary"]["runs"] == 1 and report["summary"]["attempts"] == 2
    assert report["summary"]["input_tokens"] is None
    assert report["summary"]["known_input_tokens"] == 100
    from decimal import Decimal

    assert Decimal(report["summary"]["estimated_costs"]["USD"]) == Decimal("0.0002")
    assert report["summary"]["unpriced_attempts"] == 1
    assert report["fake"]["runs"] == 0
    assert len(report["recent_runs"]) == 1 and not report["has_more"]
    assert "Private chat" not in str(report) and "Private request" not in str(report)
    detail = ai_client.get(f"/api/v1/ai/runs/{run['id']}").json()
    assert detail["price"]["date"] == "2026-10-24"
    assert ai_client.get("/api/v1/ai/usage?days=8").status_code == 422
    expired = ai_client.get("/api/v1/ai/usage?date_from=2026-01-01&date_to=2026-01-02").json()
    assert expired["retention_partial"] and expired["summary"]["runs"] == 0
    assert (
        ai_client.get("/api/v1/ai/usage?date_from=2026-01-01&date_to=2026-02-01").status_code == 422
    )
    seed_user(concurrent_engine, "usage-other@example.com", password_hash)
    browser_login(ai_client, "usage-other@example.com")
    other = ai_client.get("/api/v1/ai/usage").json()
    assert other["summary"]["attempts"] == 0 and other["recent_runs"] == []


@pytest.mark.parametrize("operation", ["cancel", "delete"])
def test_stream_cancellation_or_deletion_fences_late_tokens(
    ai_client: TestClient, operation: str
) -> None:
    started, release = Event(), Event()

    class BlockingModel(FakeChatModel):
        def _stream(self, messages, stop=None, run_manager=None, **kwargs):
            yield ChatGenerationChunk(message=AIMessageChunk(content="Visible prefix"))
            started.set()
            assert release.wait(5)
            yield ChatGenerationChunk(message=AIMessageChunk(content="LATE_PRIVATE_TEXT"))

    application = cast(FastAPI, ai_client.app)
    sessions = application.state.session_factory
    service = AiService(
        SqlAlchemyAiTransactions(sessions),
        PostgresAgentRunners(
            sessions, model=lambda: BlockingModel(responses=(AIMessage(content="unused"),))
        ),
    )
    application.dependency_overrides[get_ai] = lambda: service
    conversation = create(ai_client)
    path = f"/api/v1/ai/conversations/{conversation['id']}"
    headers = csrf_headers(ai_client)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            ai_client.post,
            path + "/messages/stream",
            headers=headers,
            json={"message": "Block", "submission_id": str(uuid4())},
        )
        try:
            assert started.wait(4)
            state = ai_client.get(path + "/state").json()
            if operation == "cancel":
                assert (
                    ai_client.post(
                        f"/api/v1/ai/runs/{state['run']['id']}/cancel", headers=headers
                    ).status_code
                    == 200
                )
            else:
                assert ai_client.delete(path, headers=headers).status_code == 204
        finally:
            release.set()
        response = future.result(timeout=5)
    assert "LATE_PRIVATE_TEXT" not in response.text
    if operation == "cancel":
        history = ai_client.get(path + "/messages").json()["items"]
        assert len(history) == 1 and history[0]["role"] == "user"
    else:
        assert ai_client.get(path + "/state").status_code == 404


def test_recent_history_pages_backwards_without_losing_the_latest_answer(
    ai_client: TestClient,
    concurrent_engine: Engine,
) -> None:
    from uuid import UUID

    conversation = create(ai_client)
    identifier = UUID(conversation["id"])
    with Session(concurrent_engine) as database, database.begin():
        row = database.get(ConversationModel, identifier)
        assert row is not None
        repository = SqlAlchemyAiRepository(database)
        for number in range(55):
            repository.append_message(
                Message(
                    id=uuid4(),
                    user_id=row.user_id,
                    conversation_id=identifier,
                    sequence=number + 1,
                    role="assistant",
                    content=f"Message {number + 1}",
                    created_at=row.created_at,
                )
            )
    path = f"/api/v1/ai/conversations/{identifier}/messages"
    recent = ai_client.get(path, params={"recent": True, "limit": 50}).json()["items"]
    assert [item["sequence"] for item in recent] == list(range(6, 56))
    older = ai_client.get(path, params={"recent": True, "before": 6, "limit": 50}).json()["items"]
    assert [item["sequence"] for item in older] == list(range(1, 6))


def test_complete_source_http_admission_progress_replay_and_result(ai_client: TestClient) -> None:
    from app.modules.ai.application.documents import DocumentAnalysisService
    from app.modules.ai.infrastructure.document_jobs import SqlAlchemyDocumentSteps
    from app.modules.ai.infrastructure.document_runtime import DocumentAgentModel

    page = ai_client.post(
        "/api/v1/notes/pages",
        headers=csrf_headers(ai_client),
        json={"title": "Lecture notes", "content": "Complete source text " * 150},
    )
    assert page.status_code == 201, page.text
    page_id = page.json()["id"]
    chat = create(ai_client)
    payload = {
        "submission_id": str(uuid4()),
        "message": "Summarize the complete notes.",
        "source_scope": {"page_ids": [page_id]},
        "full_sources": True,
    }
    path = f"/api/v1/ai/conversations/{chat['id']}/messages"
    response = ai_client.post(path, headers=csrf_headers(ai_client), json=payload)
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["status"] == "queued" and run["attempts"] == []
    repeated = ai_client.post(path, headers=csrf_headers(ai_client), json=payload)
    assert repeated.json() == run
    progress_path = f"/api/v1/ai/runs/{run['id']}/document-progress"
    assert ai_client.get(progress_path).json()["processed_characters"] == 0
    index_path = f"/api/v1/ai/sources/page/{page_id}/index"
    assert ai_client.get(index_path).json()["status"] == "unavailable"
    assert ai_client.post(index_path + "/retry").status_code == 403
    application = cast(FastAPI, ai_client.app)
    sessions = application.state.session_factory
    service = AiService(SqlAlchemyAiTransactions(sessions), PostgresAgentRunners(sessions))
    steps = SqlAlchemyDocumentSteps(sessions, service)
    processor = DocumentAnalysisService(steps, DocumentAgentModel(steps))
    from uuid import UUID

    for _ in range(30):
        if not processor.process(UUID(run["id"])):
            break
    assert ai_client.get(progress_path).json()["phase"] == "completed"
    history = ai_client.get(path).json()["items"]
    assert [item["role"] for item in history] == ["user", "assistant"]
    assert history[-1]["sources"][0]["id"] == page_id
