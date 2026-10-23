from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from typing import cast
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import HumanMessage
from sqlalchemy import Engine, delete, func, insert, inspect, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker
from test_ai_http import BASE, create, submit
from test_ai_http import ai_client as ai_client
from test_ai_http import browser_settings as browser_settings
from test_ai_http import calendar_client as calendar_client
from test_ai_http import concurrent_engine as concurrent_engine
from test_ai_http import live_client as live_client
from test_ai_http import password_hash as password_hash
from test_ai_http import settings as settings
from test_ai_persistence import ai_database as ai_database
from test_ai_persistence import migration_config, seed
from test_auth_http import browser_login, csrf_headers, seed_user

from alembic import command
from app.integrations.llm.fake import FakeChatModel
from app.modules.ai.application.lifecycle import AiService
from app.modules.ai.infrastructure import retention
from app.modules.ai.infrastructure.lifecycle import PostgresAgentRunners, SqlAlchemyAiTransactions
from app.modules.ai.infrastructure.orm import (
    ConversationModel,
    MessageModel,
    ProviderAttemptModel,
    RunModel,
    RunReceiptModel,
    ToolExecutionModel,
)
from app.modules.ai.presentation.routes import get_ai
from app.modules.users.infrastructure.orm import UserModel


def age_run(engine: Engine, run_id: str, instant: datetime, *, chat: bool = False) -> None:
    with Session(engine) as database, database.begin():
        run = database.get(RunModel, UUID(run_id))
        assert run is not None
        database.execute(
            update(RunModel)
            .where(RunModel.id == run.id)
            .values(
                created_at=instant - timedelta(seconds=5), updated_at=instant, finished_at=instant
            )
        )
        for model in (ProviderAttemptModel, ToolExecutionModel):
            database.execute(
                update(model)
                .where(model.run_id == run.id)
                .values(started_at=instant, finished_at=instant)
            )
        database.execute(
            update(ConversationModel)
            .where(ConversationModel.id == run.conversation_id)
            .values(created_at=instant - timedelta(seconds=5))
        )
        if chat:
            database.execute(
                update(ConversationModel)
                .where(ConversationModel.id == run.conversation_id)
                .values(last_user_message_at=instant)
            )


def count(engine: Engine, model: type) -> int:
    with Session(engine) as database:
        return database.scalar(select(func.count()).select_from(model)) or 0


def checkpoint_counts(engine: Engine) -> list[int]:
    with engine.connect() as connection:
        return [
            connection.scalar(text(f"SELECT count(*) FROM {name}"))
            for name in ("checkpoints", "checkpoint_blobs", "checkpoint_writes")
        ]


@pytest.mark.parametrize("empty", [False, True])
def test_exact_chat_expiry_purges_all_content_and_keeps_independent_pages(
    ai_client: TestClient, concurrent_engine: Engine, empty: bool
) -> None:
    conversation = create(ai_client)
    page = ai_client.post(
        "/api/v1/notes/pages",
        headers=csrf_headers(ai_client),
        json={"title": "Keep independent page"},
    ).json()
    instant = datetime.now(UTC)
    old = instant - timedelta(days=30)
    if empty:
        with concurrent_engine.begin() as database:
            database.execute(update(ConversationModel).values(created_at=old))
    else:
        run = submit(ai_client, conversation).json()
        age_run(concurrent_engine, run["id"], old, chat=True)
        assert all(checkpoint_counts(concurrent_engine))
    sessions = sessionmaker(concurrent_engine)
    retention.purge_expired(sessions, now=instant - timedelta(microseconds=1))
    assert count(concurrent_engine, ConversationModel) == 1
    retention.purge_expired(sessions, now=instant)
    retention.purge_expired(sessions, now=instant)
    assert (
        count(concurrent_engine, ConversationModel) == count(concurrent_engine, MessageModel) == 0
    )
    assert checkpoint_counts(concurrent_engine) == [0, 0, 0]
    assert count(concurrent_engine, RunModel) == count(concurrent_engine, ProviderAttemptModel) == 0
    assert count(concurrent_engine, ToolExecutionModel) == 0
    assert count(concurrent_engine, RunReceiptModel) == (0 if empty else 1)
    assert ai_client.get(f"/api/v1/notes/pages/{page['id']}").status_code == 200
    assert ai_client.get(f"{BASE}/conversations/{conversation['id']}/messages").status_code == 404


def test_journal_purge_keeps_completed_context_and_blocks_old_submission(
    ai_client: TestClient, concurrent_engine: Engine
) -> None:
    conversation = create(ai_client)
    old_run = submit(ai_client, conversation, "Keep completed context").json()
    with patch.object(FakeChatModel, "_generate", side_effect=RuntimeError("Synthetic failure")):
        assert submit(ai_client, conversation, "Exclude failed branch").json()["status"] == "failed"
    instant = datetime.now(UTC)
    age_run(concurrent_engine, old_run["id"], instant - timedelta(days=30))
    assert ai_client.get(f"{BASE}/runs/{old_run['id']}").status_code == 404
    assert (
        submit(
            ai_client, conversation, "Keep completed context", old_run["submission_id"]
        ).status_code
        == 409
    )
    sessions = sessionmaker(concurrent_engine)
    retention.purge_expired(sessions, now=instant)
    assert count(concurrent_engine, RunReceiptModel) == 1
    assert count(concurrent_engine, RunModel) == 1
    with patch.object(FakeChatModel, "_generate") as provider:
        assert (
            submit(
                ai_client, conversation, "Keep completed context", old_run["submission_id"]
            ).status_code
            == 409
        )
        provider.assert_not_called()
    seen = []
    original = FakeChatModel._generate

    def capture(self, messages, *args, **kwargs):
        seen.append([message.content for message in messages if isinstance(message, HumanMessage)])
        return original(self, messages, *args, **kwargs)

    with patch.object(FakeChatModel, "_generate", capture):
        assert (
            submit(ai_client, conversation, "Continue after purge").json()["status"] == "completed"
        )
    assert seen and all(
        messages == ["Keep completed context", "Continue after purge"] for messages in seen
    )
    assert (
        len(ai_client.get(f"{BASE}/conversations/{conversation['id']}/messages").json()["items"])
        == 5
    )


@pytest.mark.parametrize("unknown", [False, True])
def test_activity_records_expire_on_their_own_transition_clock(
    ai_client: TestClient, concurrent_engine: Engine, unknown: bool
) -> None:
    conversation = create(ai_client)
    run = submit(ai_client, conversation).json()
    instant = datetime.now(UTC)
    old = instant - timedelta(days=30)
    age_run(concurrent_engine, run["id"], old + timedelta(seconds=2))
    with concurrent_engine.begin() as database:
        database.execute(
            update(ProviderAttemptModel)
            .where(ProviderAttemptModel.number == 1)
            .values(
                started_at=old,
                finished_at=None if unknown else old,
                status="started" if unknown else "succeeded",
            )
        )
    application = cast(FastAPI, ai_client.app)
    sessions = application.state.session_factory
    service = AiService(
        SqlAlchemyAiTransactions(sessions), PostgresAgentRunners(sessions), now=lambda: instant
    )
    application.dependency_overrides[get_ai] = lambda: service
    visible = ai_client.get(f"{BASE}/runs/{run['id']}").json()
    assert len(visible["attempts"]) == 1 and visible["attempts"][0]["number"] == 2
    retention.purge_expired(sessions, now=instant)
    assert count(concurrent_engine, ProviderAttemptModel) == 1
    assert count(concurrent_engine, RunModel) == 1
    retention.purge_expired(sessions, now=instant + timedelta(seconds=2))
    assert count(concurrent_engine, RunModel) == 0
    assert count(concurrent_engine, RunReceiptModel) == 1
    assert count(concurrent_engine, ConversationModel) == 1


def test_stale_candidate_is_rechecked_after_owner_lock(
    ai_client: TestClient, concurrent_engine: Engine
) -> None:
    conversation = create(ai_client)
    run = submit(ai_client, conversation).json()
    instant = datetime.now(UTC)
    age_run(concurrent_engine, run["id"], instant - timedelta(days=30), chat=True)
    original = retention.lock_owner
    renewed = False

    def renew(database, user_id):
        nonlocal renewed
        if not renewed:
            renewed = True
            with concurrent_engine.begin() as other:
                other.execute(
                    update(ConversationModel).values(
                        last_user_message_at=instant - timedelta(microseconds=1)
                    )
                )
        return original(database, user_id)

    with patch.object(retention, "lock_owner", renew):
        retention.purge_expired(sessionmaker(concurrent_engine), now=instant)
    assert count(concurrent_engine, ConversationModel) == 1
    assert count(concurrent_engine, MessageModel) == 2


def test_journal_cleanup_rolls_back_and_concurrent_retries_keep_one_receipt(
    ai_client: TestClient, concurrent_engine: Engine
) -> None:
    run = submit(ai_client, create(ai_client)).json()
    instant = datetime.now(UTC)
    age_run(concurrent_engine, run["id"], instant - timedelta(days=30))
    sessions = sessionmaker(concurrent_engine)
    with patch.object(retention, "RunReceiptModel", side_effect=RuntimeError("Synthetic failure")):
        with pytest.raises(RuntimeError):
            retention.purge_expired(sessions, now=instant)
    assert count(concurrent_engine, RunModel) == 1
    assert count(concurrent_engine, ProviderAttemptModel) == 2
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(lambda _: retention.purge_expired(sessions, now=instant), range(2)))
    assert count(concurrent_engine, RunModel) == 0
    assert count(concurrent_engine, RunReceiptModel) == 1


def test_cleanup_during_call_cannot_resurrect_content_or_a_purged_run(
    ai_client: TestClient, concurrent_engine: Engine
) -> None:
    conversation = create(ai_client)
    submission_id = str(uuid4())
    entered, release = Event(), Event()
    original = FakeChatModel._generate

    def blocked(self, *args, **kwargs):
        entered.set()
        assert release.wait(10)
        return original(self, *args, **kwargs)

    sessions = sessionmaker(concurrent_engine)
    with patch.object(FakeChatModel, "_generate", blocked), ThreadPoolExecutor(1) as pool:
        pending = pool.submit(submit, ai_client, conversation, "Blocked", submission_id)
        try:
            assert entered.wait(10)
            instant = datetime.now(UTC)
            with concurrent_engine.begin() as database:
                database.execute(
                    update(ConversationModel).values(
                        created_at=instant - timedelta(days=30),
                        last_user_message_at=instant - timedelta(days=30),
                    )
                )
            retention.purge_expired(sessions, now=instant)
            assert count(concurrent_engine, ConversationModel) == 0
            assert checkpoint_counts(concurrent_engine) == [0, 0, 0]
            retention.purge_expired(sessions, now=instant + timedelta(days=30))
            assert count(concurrent_engine, RunModel) == 0
            assert count(concurrent_engine, RunReceiptModel) == 1
        finally:
            release.set()
        response = pending.result(timeout=10)
    assert response.status_code == 404
    assert (
        count(concurrent_engine, MessageModel)
        == count(concurrent_engine, ProviderAttemptModel)
        == 0
    )
    with patch.object(FakeChatModel, "_generate") as provider:
        assert submit(ai_client, create(ai_client), "Blocked", submission_id).status_code == 409
        provider.assert_not_called()


def test_receipt_migration_protects_replay_and_owner_deletion_removes_it(
    ai_database: Engine,
) -> None:
    owner = uuid4()
    with ai_database.begin() as connection:
        connection.execute(insert(UserModel).values(id=owner, email="receipt@example.com"))
        connection.execute(
            insert(RunReceiptModel).values(
                run_id=uuid4(), user_id=owner, submission_id=uuid4(), completed=True
            )
        )
        assert {
            column["name"] for column in inspect(connection).get_columns("ai_run_receipts")
        } == {"run_id", "user_id", "submission_id", "completed"}
        with pytest.raises(DBAPIError, match="Cannot downgrade"), connection.begin_nested():
            command.downgrade(migration_config(connection), "0022_ai_persistence")
        connection.execute(delete(UserModel).where(UserModel.id == owner))
        assert connection.scalar(select(func.count()).select_from(RunReceiptModel)) == 0
        command.downgrade(migration_config(connection), "0022_ai_persistence")
        command.upgrade(migration_config(connection), "head")
        command.check(migration_config(connection))


def test_cleanup_skips_busy_owners_and_handles_disabled_accounts(
    ai_client: TestClient, concurrent_engine: Engine
) -> None:
    run = submit(ai_client, create(ai_client)).json()
    instant = datetime.now(UTC)
    age_run(concurrent_engine, run["id"], instant - timedelta(days=30), chat=True)
    sessions = sessionmaker(concurrent_engine)
    with sessions.begin() as database:
        owner = database.scalar(select(UserModel).with_for_update())
        assert owner is not None
        retention.purge_expired(sessions, now=instant)
        assert count(concurrent_engine, ConversationModel) == 1
        owner.status = "disabled"
    retention.purge_expired(sessions, now=instant)
    assert count(concurrent_engine, ConversationModel) == count(concurrent_engine, RunModel) == 0
    assert count(concurrent_engine, RunReceiptModel) == 1


def test_receipt_does_not_reserve_another_owners_submission_id(
    ai_client: TestClient, concurrent_engine: Engine, password_hash: str
) -> None:
    run = submit(ai_client, create(ai_client)).json()
    instant = datetime.now(UTC)
    age_run(concurrent_engine, run["id"], instant - timedelta(days=30), chat=True)
    retention.purge_expired(sessionmaker(concurrent_engine), now=instant)
    seed_user(concurrent_engine, "other@example.com", password_hash)
    browser_login(ai_client, "other@example.com")
    response = submit(ai_client, create(ai_client), "Another owner", run["submission_id"])
    assert response.json()["status"] == "completed", response.text


def test_retention_only_setting_keeps_chat_api_disabled(ai_client: TestClient) -> None:
    application = cast(FastAPI, ai_client.app)
    application.state.settings = application.state.settings.model_copy(
        update={"ai_enabled": False, "ai_retention_enabled": True}
    )
    assert ai_client.get(f"{BASE}/conversations").status_code == 503


def test_cleanup_bounds_each_conversation_batch(ai_database: Engine) -> None:
    conversation, _ = seed(ai_database)
    instant = datetime.now(UTC)
    old = instant - timedelta(days=30)
    with ai_database.begin() as database:
        database.execute(update(ConversationModel).values(created_at=old))
        database.execute(
            insert(ConversationModel),
            [
                {
                    "id": uuid4(),
                    "user_id": conversation.user_id,
                    "title": "Synthetic",
                    "created_at": old,
                    "next_sequence": 1,
                }
                for _ in range(100)
            ],
        )
    sessions = sessionmaker(ai_database)
    retention.purge_expired(sessions, now=instant)
    assert count(ai_database, ConversationModel) == 1
    retention.purge_expired(sessions, now=instant)
    assert count(ai_database, ConversationModel) == 0
