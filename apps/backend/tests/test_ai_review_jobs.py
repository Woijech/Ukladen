from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from sqlalchemy import select, update
from test_ai_connections import configuration as configuration
from test_ai_http import ai_client as ai_client
from test_ai_http import browser_settings as browser_settings
from test_ai_http import calendar_client as calendar_client
from test_ai_http import concurrent_engine as concurrent_engine
from test_ai_http import live_client as live_client
from test_ai_http import password_hash as password_hash
from test_ai_http import settings as settings
from test_auth_http import csrf_headers

from app.integrations.llm.fake import FakeChatModel
from app.modules.ai.application.connections import ConnectionAccess
from app.modules.ai.application.lifecycle import AiService
from app.modules.ai.application.reviews import ReviewConfiguration, ReviewSettingsService
from app.modules.ai.infrastructure.lifecycle import PostgresAgentRunners, SqlAlchemyAiTransactions
from app.modules.ai.infrastructure.orm import ConversationModel, MessageModel, ProviderAttemptModel
from app.modules.ai.infrastructure.repository import SqlAlchemyAiRepository
from app.modules.ai.infrastructure.review_generation import ReviewAgentModel
from app.modules.ai.infrastructure.review_jobs import ReviewJobs
from app.modules.ai.infrastructure.review_models import ReviewModel, ReviewSettingsModel
from app.modules.ai.infrastructure.review_settings import SqlAlchemyReviewSettings
from app.modules.ai.infrastructure.sources import SqlAlchemySourceReader
from app.modules.notifications.infrastructure.orm import NotificationModel
from app.modules.tasks.infrastructure.orm import TaskModel
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication


@pytest.fixture
def reviews(ai_client: TestClient, configuration):
    from typing import cast

    application = cast(FastAPI, ai_client.app)
    now = datetime.now(UTC)
    task = ai_client.post(
        "/api/v1/tasks",
        headers=csrf_headers(ai_client),
        json={"title": "Calculus", "deadline_at": (now + timedelta(hours=2)).isoformat()},
    ).json()
    sessions = application.state.session_factory
    service = AiService(
        SqlAlchemyAiTransactions(sessions),
        PostgresAgentRunners(sessions),
        connections=ConnectionAccess(configuration),
    )
    reader = SqlAlchemySourceReader(sessions, application.state.academic_provider, 3600)
    calls = []

    def fake():
        calls.append(1)
        return FakeChatModel(responses=(AIMessage(content="Сводка по своим данным."),))

    generator = ReviewAgentModel(service, fake_factory=fake)
    jobs = ReviewJobs(service, reader, generator, enabled=lambda: True)
    with sessions.begin() as database:
        row = database.get(TaskModel, UUID(task["id"]))
        assert row is not None
        owner = row.user_id
        ReviewSettingsService(
            SqlAlchemyReviewSettings(database), SqlAlchemyUserAuthentication(database)
        ).save(
            owner,
            ReviewConfiguration(
                enabled=True, offering_id="flash", daily_time="00:00", weekly=False
            ),
            0,
            connections=service.connections,
            ai=SqlAlchemyAiRepository(database),
        )
    return jobs, owner, task, calls


def test_durable_single_call_delivery_dedup_hidden_chat_and_retention(reviews):
    jobs, owner, task, calls = reviews
    identifiers = jobs.scan()
    assert len(identifiers) == 1
    identifier = identifiers[0]
    jobs.process(identifier)
    jobs.process(identifier)
    with jobs.sessions() as database:
        row = database.get(ReviewModel, identifier)
        assert row is not None and row.status == "completed"
        conversation_id = row.conversation_id
        conversation = database.get(ConversationModel, conversation_id)
        assert conversation is not None and conversation.last_user_message_at is None
        assert SqlAlchemyAiRepository(database).list_conversations(owner, 100, 0) == []
        assert [item.role for item in database.scalars(select(MessageModel))] == ["assistant"]
        assert len(list(database.scalars(select(ProviderAttemptModel)))) == 1
        notification = database.scalar(select(NotificationModel))
        assert notification is not None and notification.kind == "ai_review"
        assert notification.review_id == identifier and notification.reminder_id is None
    assert len(calls) == 1 and jobs.scan() == []
    with jobs.sessions.begin() as database:
        database.execute(update(ReviewSettingsModel).values(next_scan_at=datetime.now(UTC)))
    assert jobs.scan() == []
    with jobs.sessions.begin() as database:
        database.execute(update(ReviewModel).values(expires_at=datetime.now(UTC)))
    jobs.recover()
    with jobs.sessions() as database:
        assert database.get(ReviewModel, identifier) is None
        assert database.get(ConversationModel, conversation_id) is None
        assert database.scalar(select(NotificationModel)) is None


@pytest.mark.parametrize("change", ["settings", "source", "connection"])
def test_revocation_or_stale_evidence_prevents_model_dispatch(reviews, change):
    jobs, owner, task, calls = reviews
    identifier = jobs.scan()[0]
    with jobs.sessions.begin() as database:
        if change == "settings":
            database.execute(update(ReviewSettingsModel).values(version=2))
        elif change == "source":
            database.execute(update(TaskModel).values(version=2, title="Changed"))
        else:
            jobs.service.connections.configuration = type(
                "Disconnected",
                (),
                {"offering": lambda *args: (_ for _ in ()).throw(ValueError("disconnected"))},
            )()
    jobs.process(identifier)
    assert calls == []
    with jobs.sessions() as database:
        row = database.get(ReviewModel, identifier)
        assert row is not None and row.status == "failed"
        assert database.scalar(select(ProviderAttemptModel)) is None
        assert database.scalar(select(NotificationModel)) is None


def test_disabled_runtime_and_unknown_provider_outcome_never_replay(reviews):
    jobs, owner, task, calls = reviews
    jobs.enabled = lambda: False
    assert jobs.scan() == []
    jobs.enabled = lambda: True
    identifier = jobs.scan()[0]

    def crash(*args):
        calls.append(1)
        raise TimeoutError("unknown outcome")

    jobs.generator.generate = crash
    jobs.process(identifier)
    jobs.process(identifier)
    jobs.recover()
    assert len(calls) == 1 and jobs.pending() == []
    with jobs.sessions() as database:
        row = database.get(ReviewModel, identifier)
        assert row is not None and row.status == "failed"
        assert database.scalar(select(NotificationModel)) is None


def test_report_http_owner_csrf_discussion_and_changed_source_fencing(
    reviews, ai_client, password_hash
):
    from test_auth_http import browser_login, seed_user

    jobs, owner, task, calls = reviews
    identifier = jobs.scan()[0]
    jobs.process(identifier)
    path = f"/api/v1/ai/reviews/{identifier}"
    report = ai_client.get(path)
    assert report.status_code == 200, report.text
    assert report.headers["cache-control"] == "no-store"
    assert report.json()["content"] == "Сводка по своим данным."
    assert ai_client.post(path + "/discuss").status_code == 403
    discussion = ai_client.post(path + "/discuss", headers=csrf_headers(ai_client))
    assert discussion.status_code == 200, discussion.text
    assert (
        ai_client.post(path + "/discuss", headers=csrf_headers(ai_client)).json()
        == discussion.json()
    )
    with jobs.sessions() as database:
        chats = SqlAlchemyAiRepository(database).list_conversations(owner, 100, 0)
        assert len(chats) == 1 and str(chats[0].id) == discussion.json()["conversation_id"]
        assert chats[0].last_user_message_at is None
    assert len(calls) == 1
    with jobs.sessions.begin() as database:
        database.execute(update(MessageModel).values(sources=[]))
        database.execute(update(TaskModel).values(version=2, title="Changed"))
    stale = ai_client.get(path).json()
    assert stale["stale"] is True and stale["content"] is None and stale["sources"] == []
    assert ai_client.post(path + "/discuss", headers=csrf_headers(ai_client)).status_code == 409
    with jobs.sessions() as database:
        engine = database.get_bind()
    seed_user(engine, "review-outsider@example.com", password_hash)
    browser_login(ai_client, "review-outsider@example.com")
    assert ai_client.get(path).status_code == 404
    assert ai_client.post(path + "/discuss", headers=csrf_headers(ai_client)).status_code == 404
    from uuid import uuid4

    assert ai_client.get(f"/api/v1/ai/reviews/{uuid4()}").status_code == 404
    ai_client.cookies.clear()
    assert ai_client.get(path).status_code == 401


def test_settings_change_during_model_call_fences_late_delivery(reviews):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    jobs, owner, task, calls = reviews
    entered, release = Event(), Event()

    class BlockingModel(FakeChatModel):
        def _generate(self, *args, **kwargs):
            entered.set()
            assert release.wait(10)
            return super()._generate(*args, **kwargs)

    jobs.generator.fake_factory = lambda: BlockingModel(responses=(AIMessage(content="Late"),))
    identifier = jobs.scan()[0]
    with ThreadPoolExecutor(1) as pool:
        pending = pool.submit(jobs.process, identifier)
        try:
            assert entered.wait(5)
            with jobs.sessions.begin() as database:
                database.execute(update(ReviewSettingsModel).values(version=2))
        finally:
            release.set()
        pending.result(timeout=10)
    with jobs.sessions() as database:
        row = database.get(ReviewModel, identifier)
        assert row is not None and row.status == "failed"
        assert database.scalar(select(NotificationModel)) is None
        assert database.scalar(select(MessageModel)) is None
        attempt = database.scalar(select(ProviderAttemptModel))
        assert attempt is not None and attempt.status == "succeeded"


def test_disconnected_scan_pauses_without_fallback_and_recovers(reviews, monkeypatch):
    from app.modules.ai.domain.connections import ConnectionUnavailable

    jobs, owner, _, calls = reviews
    config = jobs.service.connections.configuration
    with monkeypatch.context() as patcher:

        def unavailable(*args):
            raise ConnectionUnavailable("Synthetic connection is disabled.")

        patcher.setattr(config, "operator_key", unavailable)
        assert jobs.scan() == []
    with jobs.sessions.begin() as database:
        settings = database.get(ReviewSettingsModel, owner)
        assert settings is not None and settings.state["paused"] == "connection_unavailable"
        settings.next_scan_at = datetime.now(UTC)
    identifiers = jobs.scan()
    assert len(identifiers) == 1
    jobs.process(identifiers[0])
    assert len(calls) == 1
    with jobs.sessions() as database:
        settings = database.get(ReviewSettingsModel, owner)
        assert settings is not None and "paused" not in settings.state


def test_warning_batches_deliver_each_issue_once_with_a_small_input_budget(
    reviews, ai_client, tmp_path
):
    import json

    jobs, owner, first, calls = reviews
    catalog_path = tmp_path / "catalog.json"
    catalog = json.loads(catalog_path.read_text())
    catalog["entries"][0]["max_input_bytes"] = 4000
    catalog_path.write_text(json.dumps(catalog))
    due = (datetime.now(UTC) + timedelta(hours=3)).isoformat()
    identifiers = {first["id"]}
    for number in range(12):
        response = ai_client.post(
            "/api/v1/tasks",
            headers=csrf_headers(ai_client),
            json={
                "title": f"Lecture {number} " + "synthetic study details " * 7,
                "deadline_at": due,
            },
        )
        assert response.status_code == 201, response.text
        identifiers.add(response.json()["id"])
    with jobs.sessions.begin() as database:
        row = database.get(ReviewSettingsModel, owner)
        assert row is not None
        row.configuration = row.configuration | {"daily": False, "weekly": False}
        row.version += 1
        row.next_scan_at = datetime.now(UTC)
    observed = []

    class CapturingModel(FakeChatModel):
        def _generate(self, messages, *args, **kwargs):
            observed.append(json.loads(messages[-1].content))
            return super()._generate(messages, *args, **kwargs)

    jobs.generator.fake_factory = lambda: CapturingModel(
        responses=(AIMessage(content="Synthetic warning."),)
    )
    for _ in range(15):
        batch = jobs.scan()
        if not batch:
            break
        assert len(batch) == 1
        jobs.process(batch[0])
        with jobs.sessions.begin() as database:
            row = database.get(ReviewSettingsModel, owner)
            assert row is not None
            row.next_scan_at = datetime.now(UTC)
    delivered = [
        issue["task_id"]
        for payload in observed
        for issue in payload["issues"]
        if issue["kind"] == "deadline"
    ]
    assert len(observed) > 1
    assert set(delivered) == identifiers and len(delivered) == len(identifiers)
    assert all(payload["issues"] for payload in observed)
    assert calls == []


@pytest.mark.parametrize("tool_name", ["search_web", "propose_actions"])
def test_background_model_cannot_use_tools_or_execute_actions(reviews, tool_name):
    from app.modules.ai.infrastructure.orm import ToolExecutionModel

    jobs, _, task, _ = reviews
    calls = []

    def malicious():
        calls.append(1)
        return FakeChatModel(
            responses=(
                AIMessage(
                    content="",
                    usage_metadata={"input_tokens": 11, "output_tokens": 3, "total_tokens": 14},
                    tool_calls=[
                        {
                            "name": tool_name,
                            "args": {"query": "synthetic"},
                            "id": "synthetic-tool-call",
                            "type": "tool_call",
                        }
                    ],
                ),
            )
        )

    jobs.generator.fake_factory = malicious
    identifier = jobs.scan()[0]
    jobs.process(identifier)
    with jobs.sessions() as database:
        review = database.get(ReviewModel, identifier)
        assert review is not None and review.status == "failed"
        assert database.scalar(select(NotificationModel)) is None
        assert database.scalar(select(ToolExecutionModel)) is None
        original = database.get(TaskModel, UUID(task["id"]))
        assert original is not None and original.title == "Calculus" and original.version == 1
        attempts = list(database.scalars(select(ProviderAttemptModel)))
        assert len(attempts) == 1
        assert attempts[0].status == "succeeded"
        assert (attempts[0].input_tokens, attempts[0].output_tokens) == (11, 3)
    assert len(calls) == 1


def test_expiry_during_model_call_cancels_run_and_fences_late_result(reviews):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from app.modules.ai.infrastructure.orm import RunModel

    jobs, _, _, _ = reviews
    entered, release = Event(), Event()

    class BlockingModel(FakeChatModel):
        def _generate(self, *args, **kwargs):
            entered.set()
            assert release.wait(10)
            return super()._generate(*args, **kwargs)

    jobs.generator.fake_factory = lambda: BlockingModel(responses=(AIMessage(content="Late"),))
    identifier = jobs.scan()[0]
    with ThreadPoolExecutor(1) as pool:
        pending = pool.submit(jobs.process, identifier)
        try:
            assert entered.wait(5)
            with jobs.sessions.begin() as database:
                row = database.get(ReviewModel, identifier)
                assert row is not None
                row.expires_at = datetime.now(UTC)
            jobs.recover()
        finally:
            release.set()
        pending.result(timeout=10)
    with jobs.sessions() as database:
        assert database.get(ReviewModel, identifier) is None
        assert database.scalar(select(NotificationModel)) is None
        assert database.scalar(select(MessageModel)) is None
        run = database.scalar(select(RunModel))
        assert run is not None and run.status == "cancelled" and run.conversation_id is None
        attempt = database.scalar(select(ProviderAttemptModel))
        assert attempt is not None and attempt.status == "interrupted"
