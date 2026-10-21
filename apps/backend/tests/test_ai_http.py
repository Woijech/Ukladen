import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from typing import cast
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import Engine, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_ai_persistence import checkpoint_connection
from test_auth_http import browser_login, csrf_headers, seed_user
from test_calendar_http import browser_settings as browser_settings
from test_calendar_http import calendar_client as calendar_client
from test_calendar_http import concurrent_engine as concurrent_engine
from test_calendar_http import live_client as live_client
from test_calendar_http import password_hash as password_hash
from test_calendar_http import settings as settings
from test_logging import capture_json

from app.integrations.llm.fake import FakeChatModel
from app.modules.ai.application.lifecycle import AiService
from app.modules.ai.infrastructure.checkpoints import OwnedPostgresSaver
from app.modules.ai.infrastructure.lifecycle import PostgresAgentRunners, SqlAlchemyAiTransactions
from app.modules.ai.infrastructure.orm import ConversationModel, MessageModel, RunModel
from app.modules.ai.infrastructure.repository import SqlAlchemyAiRepository
from app.modules.ai.presentation.routes import get_ai

BASE = "/api/v1/ai"


@pytest.fixture
def ai_client(calendar_client: TestClient) -> Iterator[TestClient]:
    application = cast(FastAPI, calendar_client.app)
    application.state.settings = application.state.settings.model_copy(update={"ai_enabled": True})
    yield calendar_client


def create(client: TestClient) -> dict:
    response = client.post(
        f"{BASE}/conversations", headers=csrf_headers(client), json={"title": "Private chat"}
    )
    assert response.status_code == 201, response.text
    return response.json()


def submit(
    client: TestClient,
    conversation: dict,
    message: str = "Private request",
    submission_id: str | None = None,
):
    return client.post(
        f"{BASE}/conversations/{conversation['id']}/messages",
        headers=csrf_headers(client),
        json={"message": message, "submission_id": submission_id or str(uuid4())},
    )


def install_script(client: TestClient, *responses: AIMessage) -> None:
    application = cast(FastAPI, client.app)
    sessions = application.state.session_factory
    service = AiService(
        SqlAlchemyAiTransactions(sessions),
        PostgresAgentRunners(sessions, model=lambda: FakeChatModel(responses=responses)),
    )
    application.dependency_overrides[get_ai] = lambda: service


def test_owned_chat_history_accounting_replay_and_continuation(
    ai_client: TestClient, concurrent_engine: Engine
) -> None:
    with capture_json() as logs:
        conversation = create(ai_client)
        assert "user_id" not in conversation
        response = submit(ai_client, conversation)
        assert response.status_code == 200, response.text
        run = response.json()
        assert run["status"] == "completed" and run["version"] == 3
        assert len(run["attempts"]) == 2 and len(run["tools"]) == 1
        assert all(
            item["status"] == "succeeded"
            and item["input_tokens"] is None
            and item["output_tokens"] is None
            for item in run["attempts"]
        )
        assert run["tools"][0]["status"] == "succeeded"
        assert not {"request_digest", "user_id", "content", "arguments"}.intersection(run)
        repeated = submit(ai_client, conversation, submission_id=run["submission_id"])
        assert repeated.json() == run
        assert submit(ai_client, conversation, "Different", run["submission_id"]).status_code == 409
        history_path = f"{BASE}/conversations/{conversation['id']}/messages"
        messages = ai_client.get(history_path).json()["items"]
        assert [item["sequence"] for item in messages] == [1, 2]
        assert [item["role"] for item in messages] == ["user", "assistant"]
        assert (
            ai_client.get(history_path, params={"after": 1, "limit": 1}).json()["items"]
            == messages[1:]
        )
        assert ai_client.get(f"{BASE}/runs/{run['id']}").json() == run
        assert len(ai_client.get(f"{BASE}/conversations").json()["items"]) == 1
        second = submit(ai_client, conversation, "Second request")
        assert second.json()["status"] == "completed", second.text
        assert len(ai_client.get(history_path).json()["items"]) == 4
    assert "Private chat" not in logs.getvalue() and "Private request" not in logs.getvalue()
    assert response.headers["cache-control"] == "no-store"
    with Session(concurrent_engine) as database:
        row = database.get(ConversationModel, UUID(conversation["id"]))
        assert row is not None
        owner = row.user_id
    with checkpoint_connection(concurrent_engine) as connection:
        checkpoint = OwnedPostgresSaver(connection, owner, UUID(conversation["id"])).get_tuple(
            {"configurable": {"thread_id": conversation["id"]}}
        )
        assert checkpoint is not None
        assert [
            message.content
            for message in checkpoint.checkpoint["channel_values"]["messages"]
            if isinstance(message, HumanMessage)
        ] == ["Private request", "Second request"]


def test_ownership_session_and_csrf_cover_every_endpoint(
    ai_client: TestClient, concurrent_engine: Engine, password_hash: str
) -> None:
    conversation = create(ai_client)
    run = submit(ai_client, conversation).json()
    path = f"{BASE}/conversations/{conversation['id']}"
    for method, url, payload in (
        ("POST", f"{BASE}/conversations", {"title": "T"}),
        ("POST", path + "/messages", {"message": "T", "submission_id": str(uuid4())}),
        ("POST", f"{BASE}/runs/{run['id']}/cancel", None),
        ("DELETE", path, None),
    ):
        assert ai_client.request(method, url, json=payload).status_code == 403
        assert (
            ai_client.request(
                method,
                url,
                headers=csrf_headers(ai_client) | {"Origin": "https://attacker.example"},
                json=payload,
            ).status_code
            == 403
        )
    seed_user(concurrent_engine, "other@example.com", password_hash)
    browser_login(ai_client, "other@example.com")
    assert ai_client.get(f"{BASE}/conversations").json()["items"] == []
    assert ai_client.get(path + "/messages").status_code == 404
    assert ai_client.get(f"{BASE}/runs/{run['id']}").status_code == 404
    assert submit(ai_client, conversation).status_code == 404
    assert (
        ai_client.post(
            f"{BASE}/runs/{run['id']}/cancel", headers=csrf_headers(ai_client)
        ).status_code
        == 404
    )
    assert ai_client.delete(path, headers=csrf_headers(ai_client)).status_code == 404
    ai_client.cookies.clear()
    assert ai_client.get(f"{BASE}/conversations").status_code == 401
    assert ai_client.get(path + "/messages").status_code == 401
    assert ai_client.get(f"{BASE}/runs/{run['id']}").status_code == 401


@pytest.mark.parametrize(
    "payload",
    [
        {"message": " "},
        {"message": "я" * 8193},
        {"message": "\ud800"},
        {"message": "x\x00y"},
        {"submission_id": "invalid"},
        {"owner_id": str(uuid4())},
        {"provider": "external"},
        {"tools": ["sql"]},
        {"message": "x" * 16385},
    ],
)
def test_bounded_inputs_cannot_override_execution_context(
    ai_client: TestClient, payload: dict
) -> None:
    conversation = create(ai_client)
    response = ai_client.post(
        f"{BASE}/conversations/{conversation['id']}/messages",
        headers=csrf_headers(ai_client) | {"Content-Type": "application/json"},
        content=json.dumps({"message": "T", "submission_id": str(uuid4())} | payload),
    )
    assert response.status_code == 422
    assert "owner_id" not in response.text and "я" not in response.text
    assert (
        ai_client.get(f"{BASE}/conversations/{conversation['id']}/messages").json()["items"] == []
    )


def test_disabled_ai_and_incomplete_registration_cannot_enter_module(
    ai_client: TestClient, concurrent_engine: Engine, password_hash: str
) -> None:
    application = cast(FastAPI, ai_client.app)
    application.state.settings = application.state.settings.model_copy(update={"ai_enabled": False})
    assert ai_client.get(f"{BASE}/conversations").status_code == 503
    application.state.settings = application.state.settings.model_copy(update={"ai_enabled": True})
    seed_user(concurrent_engine, "incomplete@example.com", password_hash, verified=False)
    browser_login(ai_client, "incomplete@example.com")
    assert ai_client.get(f"{BASE}/conversations").status_code == 403


@pytest.mark.parametrize("title", [" ", "x" * 201, "\ud800", "x\x00y", ""])
def test_invalid_chat_titles_are_rejected_before_storage(ai_client: TestClient, title: str) -> None:
    response = ai_client.post(
        f"{BASE}/conversations",
        headers=csrf_headers(ai_client) | {"Content-Type": "application/json"},
        content=json.dumps({"title": title}),
    )
    assert response.status_code == 422
    assert ai_client.get(f"{BASE}/conversations").json()["items"] == []


def test_unknown_and_measured_zero_usage_and_provider_failure(ai_client: TestClient) -> None:
    conversation = create(ai_client)
    install_script(
        ai_client,
        AIMessage(
            content="Measured",
            usage_metadata={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        ),
    )
    run = submit(ai_client, conversation).json()
    assert len(run["attempts"]) == 1 and run["tools"] == []
    assert run["attempts"][0]["input_tokens"] == run["attempts"][0]["output_tokens"] == 0
    with (
        patch.object(FakeChatModel, "_generate", side_effect=RuntimeError("private-provider-body")),
        capture_json() as logs,
    ):
        failed = submit(ai_client, conversation, "Fail")
    assert failed.json()["status"] == "failed"
    assert len(failed.json()["attempts"]) == 1
    assert failed.json()["attempts"][0]["status"] == "failed"
    assert "private-provider-body" not in logs.getvalue() and "private" not in failed.text
    cast(FastAPI, ai_client.app).dependency_overrides.pop(get_ai)
    assert submit(ai_client, conversation, "Recover").json()["status"] == "completed"


@pytest.mark.parametrize("operation", ["cancel", "delete"])
def test_pending_submission_replay_busy_conflict_and_interruption_stop_dispatch(
    ai_client: TestClient, concurrent_engine: Engine, operation: str
) -> None:
    conversation = create(ai_client)
    headers = csrf_headers(ai_client)
    submission_id = str(uuid4())
    entered, release = Event(), Event()
    original = FakeChatModel._generate

    def blocked(self, *args, **kwargs):
        if not entered.is_set():
            entered.set()
            assert release.wait(10)
        return original(self, *args, **kwargs)

    with patch.object(FakeChatModel, "_generate", blocked), ThreadPoolExecutor(1) as pool:
        pending = pool.submit(submit, ai_client, conversation, "Blocked", submission_id)
        try:
            assert entered.wait(10)
            replay = submit(ai_client, conversation, "Blocked", submission_id)
            run = replay.json()
            assert run["status"] == "running" and len(run["attempts"]) == 1
            assert submit(ai_client, conversation, "Other").status_code == 409
            if operation == "cancel":
                interrupted = ai_client.post(f"{BASE}/runs/{run['id']}/cancel", headers=headers)
                assert interrupted.json()["status"] == "cancelled"
                # The old model is still blocked while a new run completes in this chat.
                next_turn = submit(ai_client, conversation, "Next turn")
                assert next_turn.json()["status"] == "completed", next_turn.text
            else:
                assert (
                    ai_client.delete(
                        f"{BASE}/conversations/{conversation['id']}", headers=headers
                    ).status_code
                    == 204
                )
        finally:
            release.set()
        result = pending.result(timeout=10)
    assert result.json()["status"] == "cancelled", result.text
    assert len(result.json()["attempts"]) == 1 and result.json()["tools"] == []
    assert result.json()["attempts"][0]["status"] == "interrupted"
    if operation == "cancel":
        assert (
            len(
                ai_client.get(f"{BASE}/conversations/{conversation['id']}/messages").json()["items"]
            )
            == 3
        )
    else:
        assert (
            ai_client.get(f"{BASE}/conversations/{conversation['id']}/messages").status_code == 404
        )
        assert result.json()["conversation_id"] is None
        assert submit(ai_client, create(ai_client), "Blocked", submission_id).status_code == 409
    with Session(concurrent_engine) as database:
        assert database.scalar(select(func.count()).select_from(RunModel)) == (
            2 if operation == "cancel" else 1
        )


def test_expiry_filters_reads_and_cannot_be_renewed_by_new_submission(
    ai_client: TestClient, concurrent_engine: Engine
) -> None:
    conversation = create(ai_client)
    with concurrent_engine.begin() as database:
        database.execute(
            update(ConversationModel).values(created_at=datetime.now(UTC) - timedelta(days=30))
        )
    assert ai_client.get(f"{BASE}/conversations").json()["items"] == []
    assert ai_client.get(f"{BASE}/conversations/{conversation['id']}/messages").status_code == 404
    assert submit(ai_client, conversation).status_code == 404


def test_failed_admission_rolls_back_and_failed_completion_does_not_replay_calls(
    ai_client: TestClient, concurrent_engine: Engine
) -> None:
    conversation = create(ai_client)
    original = SqlAlchemyAiRepository.append_message

    def fail(repository, message):
        original(repository, message)
        raise SQLAlchemyError("private-database-details")

    with patch.object(SqlAlchemyAiRepository, "append_message", fail):
        assert submit(ai_client, conversation).status_code == 503
    with Session(concurrent_engine) as database:
        assert database.scalar(select(func.count()).select_from(RunModel)) == 0
        assert database.scalar(select(func.count()).select_from(MessageModel)) == 0

    def fail_completion(repository, message):
        original(repository, message)
        if message.role == "assistant":
            raise SQLAlchemyError("private-database-details")

    submission_id = str(uuid4())
    with patch.object(SqlAlchemyAiRepository, "append_message", fail_completion):
        assert submit(ai_client, conversation, submission_id=submission_id).status_code == 503
    replay = submit(ai_client, conversation, submission_id=submission_id).json()
    assert (
        replay["status"] == "running" and len(replay["attempts"]) == 2 and len(replay["tools"]) == 1
    )
    assert (
        len(ai_client.get(f"{BASE}/conversations/{conversation['id']}/messages").json()["items"])
        == 1
    )


def test_chat_deletion_preserves_pages_and_safe_journal(ai_client: TestClient) -> None:
    conversation = create(ai_client)
    page = ai_client.post(
        "/api/v1/notes/pages", headers=csrf_headers(ai_client), json={"title": "Keep page"}
    ).json()
    run = submit(ai_client, conversation).json()
    assert (
        ai_client.delete(
            f"{BASE}/conversations/{conversation['id']}", headers=csrf_headers(ai_client)
        ).status_code
        == 204
    )
    assert ai_client.get(f"/api/v1/notes/pages/{page['id']}").status_code == 200
    journal = ai_client.get(f"{BASE}/runs/{run['id']}").json()
    assert journal["conversation_id"] is None and journal["status"] == "completed"
    assert "Private request" not in str(journal)
