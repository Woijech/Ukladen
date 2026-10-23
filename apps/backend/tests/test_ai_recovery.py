import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import Event
from typing import cast
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session, sessionmaker
from test_ai_agent import tool_message
from test_ai_http import BASE, create, install_script, submit
from test_ai_http import ai_client as ai_client
from test_ai_http import browser_settings as browser_settings
from test_ai_http import calendar_client as calendar_client
from test_ai_http import concurrent_engine as concurrent_engine
from test_ai_http import live_client as live_client
from test_ai_http import password_hash as password_hash
from test_ai_http import settings as settings
from test_ai_persistence import ai_database as ai_database
from test_ai_persistence import make_run, seed
from test_auth_http import csrf_headers

from app.integrations.llm.fake import FakeChatModel
from app.modules.ai.application.agent import AgentInput, AgentReview, InvalidAgentReview
from app.modules.ai.application.lifecycle import AiService, RunJournal
from app.modules.ai.domain.state import ProviderAttempt, ToolExecution
from app.modules.ai.infrastructure.agent import OfflineAgentRunner
from app.modules.ai.infrastructure.checkpoints import owned_offline_runner
from app.modules.ai.infrastructure.fake_tools import fake_reviewed_double
from app.modules.ai.infrastructure.lifecycle import PostgresAgentRunners, SqlAlchemyAiTransactions
from app.modules.ai.infrastructure.orm import RunModel
from app.modules.ai.infrastructure.recovery import reconcile_runs
from app.modules.ai.infrastructure.repository import SqlAlchemyAiRepository
from app.modules.ai.presentation.routes import get_ai
from app.modules.users.infrastructure.orm import UserModel


@pytest.mark.parametrize("queued", [False, True])
def test_exact_recovery_boundary_preserves_pause_and_closes_unknown_outcomes(
    ai_database: Engine, queued: bool
) -> None:
    conversation, _ = seed(ai_database)
    instant = datetime.now(UTC)
    created = instant - timedelta(seconds=60)
    run = replace(make_run(conversation), created_at=created, updated_at=created)
    sessions = sessionmaker(ai_database)
    with sessions.begin() as database:
        repository = SqlAlchemyAiRepository(database)
        repository.create_run(run)
        if not queued:
            running = run.transition("running", created)
            repository.save_run(running, "queued")
            repository.create_attempt(
                ProviderAttempt(
                    id=uuid4(),
                    user_id=run.user_id,
                    run_id=run.id,
                    number=1,
                    status="started",
                    started_at=created,
                )
            )
            repository.create_tool_execution(
                ToolExecution(
                    id=uuid4(),
                    user_id=run.user_id,
                    run_id=run.id,
                    number=1,
                    call_id="synthetic",
                    tool_name="fake_double",
                    status="started",
                    started_at=created,
                )
            )
    assert reconcile_runs(sessions, now=instant - timedelta(microseconds=1)) == 0
    assert reconcile_runs(sessions, now=instant) == 1
    assert reconcile_runs(sessions, now=instant) == 0
    with sessions() as database:
        repository = SqlAlchemyAiRepository(database)
        stored = repository.get_run(run.user_id, run.id)
        assert stored is not None and stored.status == "failed" and stored.finished_at == instant
        for execution in [
            *repository.attempts(run.user_id, run.id),
            *repository.tool_executions(run.user_id, run.id),
        ]:
            assert execution.status == "interrupted" and execution.error_code == "interrupted"
        if not queued:
            attempt = repository.attempts(run.user_id, run.id)[0]
            assert attempt.input_tokens is attempt.output_tokens is None


def test_recovery_skips_locked_owner_and_preserves_review_pauses(ai_database: Engine) -> None:
    conversation, _ = seed(ai_database)
    instant = datetime.now(UTC)
    created = instant - timedelta(seconds=60)
    run = replace(make_run(conversation), created_at=created, updated_at=created)
    sessions = sessionmaker(ai_database)
    with sessions.begin() as database:
        SqlAlchemyAiRepository(database).create_run(run)
    with sessions.begin() as database:
        database.scalar(select(UserModel).where(UserModel.id == run.user_id).with_for_update())
        assert reconcile_runs(sessions, now=instant) == 0
    with sessions.begin() as database:
        repository = SqlAlchemyAiRepository(database)
        running = run.transition("running", created)
        repository.save_run(running, "queued")
        repository.save_run(running.transition("interrupted", created), "running")
    assert reconcile_runs(sessions, now=instant) == 0
    with sessions.begin() as database:
        repository = SqlAlchemyAiRepository(database)
        current = repository.get_run(run.user_id, run.id)
        assert current is not None and current.status == "interrupted"
        repository.save_run(current.transition("running", created), "interrupted")
        database.execute(
            update(UserModel).where(UserModel.id == run.user_id).values(status="disabled")
        )
    assert reconcile_runs(sessions, now=instant) == 1


def test_crashed_process_reconciles_in_fresh_process_without_replaying_provider(
    ai_database: Engine,
) -> None:
    conversation, _ = seed(ai_database)
    url = ai_database.url.render_as_string(hide_password=False)
    schema = ai_database.dialect.default_schema_name
    assert schema is not None
    submission_id = uuid4()
    child = """
import os, sys
from uuid import UUID
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.integrations.llm.fake import FakeChatModel
from app.modules.ai.application.agent import AgentInput
from app.modules.ai.application.lifecycle import AiService
from app.modules.ai.infrastructure.lifecycle import PostgresAgentRunners, SqlAlchemyAiTransactions
engine = create_engine(sys.argv[1], connect_args={'options': '-csearch_path=' + sys.argv[2]})
sessions = sessionmaker(engine)
service = AiService(SqlAlchemyAiTransactions(sessions), PostgresAgentRunners(sessions))
with patch.object(FakeChatModel, '_generate', side_effect=lambda *a, **k: os._exit(23)):
    service.submit(UUID(sys.argv[3]),
                   AgentInput(conversation_id=UUID(sys.argv[4]), message='Crash'),
                   UUID(sys.argv[5]))
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            child,
            url,
            schema,
            str(conversation.user_id),
            str(conversation.id),
            str(submission_id),
        ],
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 23, result.stderr.decode()
    sessions = sessionmaker(ai_database)
    with sessions() as database:
        run = SqlAlchemyAiRepository(database).submission(conversation.user_id, submission_id)
        assert run is not None and run.status == "running"
    recovery = """
import sys
from datetime import datetime
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.integrations.llm.fake import FakeChatModel
from app.modules.ai.infrastructure.recovery import reconcile_runs
engine = create_engine(sys.argv[1], connect_args={'options': '-csearch_path=' + sys.argv[2]})
with patch.object(FakeChatModel, '_generate') as provider:
    assert reconcile_runs(sessionmaker(engine), now=datetime.fromisoformat(sys.argv[3])) == 1
    provider.assert_not_called()
engine.dispose()
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            recovery,
            url,
            schema,
            (run.created_at + timedelta(seconds=60)).isoformat(),
        ],
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr.decode()
    service = AiService(SqlAlchemyAiTransactions(sessions), PostgresAgentRunners(sessions))
    with patch.object(FakeChatModel, "_generate") as provider:
        replay = service.submit(
            conversation.user_id,
            AgentInput(conversation_id=conversation.id, message="Crash"),
            submission_id,
        )
        assert replay.run.status == "failed" and len(replay.attempts) == 1
        assert replay.attempts[0].status == "interrupted"
        assert replay.attempts[0].input_tokens is replay.attempts[0].output_tokens is None
        provider.assert_not_called()
    assert (
        service.submit(
            conversation.user_id,
            AgentInput(conversation_id=conversation.id, message="Next"),
            uuid4(),
        ).run.status
        == "completed"
    )


@pytest.mark.parametrize("operation", ["timeout", "cancel", "reconcile"])
def test_owned_timeout_cancel_race_closes_ledger_and_rejects_late_answer(
    ai_client: TestClient, concurrent_engine: Engine, operation: str
) -> None:
    conversation = create(ai_client)
    headers = csrf_headers(ai_client)
    application = cast(FastAPI, ai_client.app)
    sessions = application.state.session_factory
    application.dependency_overrides[get_ai] = lambda: AiService(
        SqlAlchemyAiTransactions(sessions), PostgresAgentRunners(sessions)
    )
    entered, release, finished = Event(), Event(), Event()
    original = FakeChatModel._generate
    original_init = OfflineAgentRunner.__init__

    def bounded(self, *args, **kwargs):
        kwargs["run_timeout"] = 0.5
        original_init(self, *args, **kwargs)

    def blocked(self, *args, **kwargs):
        entered.set()
        try:
            assert release.wait(10)
            return original(self, *args, **kwargs)
        finally:
            finished.set()

    with (
        patch.object(OfflineAgentRunner, "__init__", bounded),
        patch.object(FakeChatModel, "_generate", blocked),
        ThreadPoolExecutor(1) as pool,
    ):
        pending = pool.submit(submit, ai_client, conversation)
        try:
            assert entered.wait(10)
            with Session(concurrent_engine) as database:
                row = database.scalar(select(RunModel))
                assert row is not None
                run_id = row.id
                recovery_time = row.created_at + timedelta(seconds=60)
            if operation == "cancel":
                response = ai_client.post(f"{BASE}/runs/{run_id}/cancel", headers=headers)
                assert response.json()["status"] == "cancelled"
            elif operation == "reconcile":
                assert reconcile_runs(sessions, now=recovery_time) == 1
            response = pending.result(timeout=5)
            run = response.json()
            assert run["status"] == ("cancelled" if operation == "cancel" else "failed"), (
                response.text
            )
            assert len(run["attempts"]) == 1 and run["tools"] == []
            assert run["attempts"][0]["status"] == "interrupted"
            assert (
                run["attempts"][0]["error_code"]
                == {"timeout": "timeout", "cancel": "cancelled", "reconcile": "interrupted"}[
                    operation
                ]
            )
            assert not finished.is_set()
        finally:
            release.set()
            assert finished.wait(10)
    assert (
        len(ai_client.get(f"{BASE}/conversations/{conversation['id']}/messages").json()["items"])
        == 1
    )
    assert ai_client.get(f"{BASE}/runs/{run_id}").json() == run
    assert submit(ai_client, conversation, "Next").json()["status"] == "completed"


def test_real_retry_ledger_and_exhaustion_do_not_fabricate_an_extra_attempt(
    ai_client: TestClient,
) -> None:
    conversation = create(ai_client)
    original = FakeChatModel._generate
    calls = 0

    def transient(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls % 2:
            raise ConnectionError("private provider details")
        return original(self, *args, **kwargs)

    with patch.object(FakeChatModel, "_generate", transient):
        run = submit(ai_client, conversation).json()
    assert run["status"] == "completed" and calls == 4
    assert [attempt["status"] for attempt in run["attempts"]] == [
        "failed",
        "succeeded",
        "failed",
        "succeeded",
    ]
    assert all(
        attempt["input_tokens"] is attempt["output_tokens"] is None for attempt in run["attempts"]
    )
    install_script(
        ai_client,
        tool_message(call_id="one"),
        tool_message(call_id="two"),
        AIMessage(content="Unused"),
    )
    calls = 0
    with patch.object(FakeChatModel, "_generate", transient):
        run = submit(ai_client, conversation, "Exhaust").json()
    assert run["status"] == "failed" and calls == len(run["attempts"]) == 4
    assert all(attempt["status"] != "started" for attempt in run["attempts"])


def test_recovery_rolls_back_outcome_changes_and_concurrent_sweeps_are_idempotent(
    ai_database: Engine,
) -> None:
    conversation, _ = seed(ai_database)
    instant = datetime.now(UTC)
    created = instant - timedelta(seconds=60)
    run = replace(make_run(conversation), created_at=created, updated_at=created)
    sessions = sessionmaker(ai_database)
    with sessions.begin() as database:
        repository = SqlAlchemyAiRepository(database)
        repository.create_run(run)
        repository.save_run(run.transition("running", created), "queued")
        repository.create_attempt(
            ProviderAttempt(
                id=uuid4(),
                user_id=run.user_id,
                run_id=run.id,
                number=1,
                status="started",
                started_at=created,
            )
        )
    with patch.object(
        SqlAlchemyAiRepository, "save_run", side_effect=RuntimeError("storage failed")
    ):
        with pytest.raises(RuntimeError):
            reconcile_runs(sessions, now=instant)
    with sessions() as database:
        assert SqlAlchemyAiRepository(database).attempts(run.user_id, run.id)[0].status == "started"
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: reconcile_runs(sessions, now=instant), range(2)))
    assert sum(results) == 1


def test_owned_review_resume_keeps_durable_attempt_budget_in_new_runners(
    ai_database: Engine,
) -> None:
    from test_ai_persistence import checkpoint_connection

    conversation, _ = seed(ai_database)
    now = datetime.now(UTC)
    run = replace(make_run(conversation), created_at=now, updated_at=now)
    sessions = sessionmaker(ai_database)
    service = AiService(SqlAlchemyAiTransactions(sessions), PostgresAgentRunners(sessions))
    with sessions.begin() as database:
        repository = SqlAlchemyAiRepository(database)
        repository.create_run(run)
        run = run.transition("running", now)
        repository.save_run(run, "queued")
    model = FakeChatModel(
        responses=(
            tool_message("fake_reviewed_double", call_id="one"),
            tool_message("fake_reviewed_double", call_id="two"),
            AIMessage(content="Must not bypass budget"),
        )
    )
    original = FakeChatModel._generate
    calls = 0

    def transient(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls % 2:
            raise ConnectionError("Synthetic retry")
        return original(self, *args, **kwargs)

    with patch.object(FakeChatModel, "_generate", transient):
        review = None
        for turn in range(3):
            with checkpoint_connection(ai_database) as connection:
                runner = owned_offline_runner(
                    connection,
                    run.user_id,
                    conversation.id,
                    model,
                    [fake_reviewed_double],
                    review_tools=frozenset({"fake_reviewed_double"}),
                    run_id=run.id,
                    journal=RunJournal(service, run),
                )
                if review is None:
                    result = runner.run(
                        AgentInput(conversation_id=conversation.id, message="Review")
                    )
                else:
                    result = runner.resume(conversation.id, review)
                if turn < 2:
                    assert result.status == "interrupted" and result.review is not None
                    review = AgentReview(
                        interrupt_id=result.review.interrupt_id, decisions=("approve",)
                    )
                else:
                    assert result.status == "failed"
                    assert review is not None
                    with pytest.raises(InvalidAgentReview):
                        runner.resume(conversation.id, review)
            if turn < 2:
                with sessions.begin() as database:
                    repository = SqlAlchemyAiRepository(database)
                    paused = run.transition("interrupted", datetime.now(UTC))
                    repository.save_run(paused, "running")
                    run = paused.transition("running", datetime.now(UTC))
                    repository.save_run(run, "interrupted")
    assert calls == 4
    with sessions() as database:
        repository = SqlAlchemyAiRepository(database)
        assert len(repository.attempts(run.user_id, run.id)) == 4
        tools = repository.tool_executions(run.user_id, run.id)
        assert len(tools) == 2 and all(tool.status == "succeeded" for tool in tools)
