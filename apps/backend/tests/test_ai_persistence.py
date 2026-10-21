import json
import os
import subprocess
import sys
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from typing import cast
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import Checkpoint, empty_checkpoint
from psycopg import Connection as PgConnection
from psycopg.errors import LockNotAvailable
from psycopg.rows import DictRow, dict_row
from sqlalchemy import Connection, Engine, create_engine, delete, func, insert, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema

from alembic import command
from app.db.session import Base
from app.modules.ai.domain.state import (
    AiConflict,
    AiNotFound,
    AiPersistenceUnavailable,
    Conversation,
    Message,
    ProviderAttempt,
    Run,
    ToolExecution,
)
from app.modules.ai.infrastructure import checkpoint_schema
from app.modules.ai.infrastructure.checkpoints import OwnedPostgresSaver
from app.modules.ai.infrastructure.orm import ConversationModel, RunModel
from app.modules.ai.infrastructure.repository import SqlAlchemyAiRepository
from app.modules.users.infrastructure.orm import UserModel

NOW = datetime.now(UTC)


def migration_config(connection: Connection) -> Config:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


@pytest.fixture
def ai_database() -> Iterator[Engine]:
    url = os.environ.get("AI_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set AI_TEST_DATABASE_URL to an explicitly disposable PostgreSQL target.")
    schema = f"ai_test_{uuid4().hex}"
    control = create_engine(url, connect_args={"connect_timeout": 3})
    engine = create_engine(
        url, connect_args={"connect_timeout": 3, "options": f"-csearch_path={schema}"}
    )
    try:
        with control.begin() as connection:
            connection.execute(CreateSchema(schema))
        with engine.begin() as connection:
            command.upgrade(migration_config(connection), "head")
        yield engine
    finally:
        engine.dispose()
        with control.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True, if_exists=True))
        control.dispose()


def seed(engine: Engine) -> tuple[Conversation, UUID]:
    user_id, other_id = uuid4(), uuid4()
    conversation = Conversation(id=uuid4(), user_id=user_id, title="Synthetic", created_at=NOW)
    with Session(engine) as database, database.begin():
        database.add_all(
            [
                UserModel(id=user_id, email="owner@example.com"),
                UserModel(id=other_id, email="other@example.com"),
            ]
        )
        database.flush()
        SqlAlchemyAiRepository(database).create_conversation(conversation)
    return conversation, other_id


def make_run(conversation: Conversation) -> Run:
    return Run(
        id=uuid4(),
        user_id=conversation.user_id,
        conversation_id=conversation.id,
        submission_id=uuid4(),
        request_digest="a" * 64,
        provider="fake",
        model="fake-v1",
        status="queued",
        created_at=NOW,
        updated_at=NOW,
    )


def make_message(conversation: Conversation, sequence: int = 1) -> Message:
    return Message(
        id=uuid4(),
        user_id=conversation.user_id,
        conversation_id=conversation.id,
        sequence=sequence,
        role="user",
        content="Synthetic",
        created_at=NOW,
    )


def checkpoint_connection(engine: Engine) -> PgConnection[DictRow]:
    dsn = engine.url.set(drivername="postgresql").render_as_string(hide_password=False)
    return PgConnection[DictRow].connect(
        dsn,
        autocommit=True,
        row_factory=dict_row,
        connect_timeout=3,
        options=f"-csearch_path={engine.dialect.default_schema_name}",
    )


def config(conversation: Conversation) -> RunnableConfig:
    return {"configurable": {"thread_id": str(conversation.id), "checkpoint_ns": ""}}


def save_checkpoint(saver: OwnedPostgresSaver, conversation: Conversation) -> RunnableConfig:
    checkpoint = empty_checkpoint()
    checkpoint["channel_values"] = {"messages": [HumanMessage(content="Synthetic private body")]}
    checkpoint["channel_versions"] = {"messages": "1"}
    saved = saver.put(config(conversation), checkpoint, {}, {"messages": "1"})
    saver.put_writes(saved, [("result", "Synthetic tool result")], "task-1")
    return saved


def test_migration_preserves_existing_user_and_refuses_populated_downgrade(
    ai_database: Engine,
) -> None:
    with ai_database.begin() as connection:
        migration = migration_config(connection)
        command.downgrade(migration, "0021_google_email_confirmations")
        user_id = uuid4()
        connection.execute(insert(UserModel).values(id=user_id, email="existing@example.com"))
        command.upgrade(migration, "head")
        command.check(migration)
        assert (
            connection.scalar(select(UserModel.email).where(UserModel.id == user_id))
            == "existing@example.com"
        )
        connection.execute(
            insert(ConversationModel).values(
                id=uuid4(),
                user_id=user_id,
                title="Keep this content",
                created_at=NOW,
                next_sequence=1,
            )
        )
        with pytest.raises(DBAPIError, match="Cannot downgrade"), connection.begin_nested():
            command.downgrade(migration, "0021_google_email_confirmations")
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "0022_ai_persistence"
        )
        assert connection.scalar(select(func.count()).select_from(ConversationModel)) == 1


def test_repositories_round_trip_owner_filters_order_versions_and_unknown_usage(
    ai_database: Engine,
) -> None:
    conversation, other_id = seed(ai_database)
    run = make_run(conversation)
    message = make_message(conversation)
    attempt = ProviderAttempt(
        id=uuid4(), user_id=run.user_id, run_id=run.id, number=1, status="started", started_at=NOW
    )
    tool = ToolExecution(
        id=uuid4(),
        user_id=run.user_id,
        run_id=run.id,
        number=1,
        call_id="call-1",
        tool_name="fake_double",
        status="started",
        started_at=NOW,
    )
    with Session(ai_database) as database, database.begin():
        repository = SqlAlchemyAiRepository(database)
        repository.append_message(message)
        repository.append_message(
            replace(
                message,
                id=uuid4(),
                sequence=2,
                role="assistant",
                created_at=NOW + timedelta(seconds=1),
            )
        )
        repository.create_run(run)
        repository.create_attempt(attempt)
        repository.create_tool_execution(tool)
        running = run.transition("running", NOW)
        repository.save_run(running, "queued")
        resumed = running.transition("interrupted", NOW).transition("running", NOW)
        repository.save_run(running.transition("interrupted", NOW), "running")
        repository.save_run(resumed, "interrupted")
        with pytest.raises(AiConflict):
            repository.save_run(running.transition("completed", NOW), "running")
        repository.save_attempt(
            replace(attempt, status="succeeded", finished_at=NOW, output_tokens=0)
        )
        repository.save_tool_execution(replace(tool, status="succeeded", finished_at=NOW))
    with Session(ai_database) as database:
        repository = SqlAlchemyAiRepository(database)
        stored = repository.get_conversation(run.user_id, conversation.id)
        assert stored == replace(conversation, next_sequence=3, last_user_message_at=NOW)
        assert [
            item.sequence for item in repository.messages(run.user_id, conversation.id, 0, 20)
        ] == [1, 2]
        assert repository.get_run(run.user_id, run.id) == resumed
        assert repository.submission(run.user_id, run.submission_id) == resumed
        assert repository.attempts(run.user_id, run.id)[0].input_tokens is None
        assert repository.attempts(run.user_id, run.id)[0].output_tokens == 0
        assert repository.tool_executions(run.user_id, run.id)[0].status == "succeeded"
        assert repository.get_conversation(other_id, conversation.id) is None
        assert repository.get_run(other_id, run.id) is None
        assert repository.submission(other_id, run.submission_id) is None
        assert repository.list_conversations(other_id, 20, 0) == []
        assert repository.messages(other_id, conversation.id, 0, 20) == []
        assert repository.attempts(other_id, run.id) == []
        assert repository.tool_executions(other_id, run.id) == []
        with pytest.raises(AiNotFound):
            repository.create_run(replace(run, id=uuid4(), user_id=other_id))


@pytest.mark.parametrize(
    "violation",
    [
        "foreign_message",
        "foreign_run",
        "foreign_attempt",
        "foreign_tool",
        "message_sequence",
        "active_run",
        "submission",
        "attempt_budget",
        "tool_budget",
        "message_bytes",
        "negative_usage",
        "orphan_checkpoint",
    ],
)
def test_database_constraints_reject_invalid_records(ai_database: Engine, violation: str) -> None:
    conversation, other_id = seed(ai_database)
    run = make_run(conversation)
    message = make_message(conversation)
    with Session(ai_database) as database, database.begin():
        repository = SqlAlchemyAiRepository(database)
        repository.append_message(message)
        repository.create_run(run)
    table = "ai_messages"
    values = asdict(replace(message, id=uuid4(), sequence=2))
    if violation.startswith("foreign"):
        values["user_id"] = other_id
    if violation in ("foreign_run", "active_run", "submission"):
        table = "ai_runs"
        values = asdict(replace(run, id=uuid4(), submission_id=uuid4()))
        if violation == "foreign_run":
            values.update(user_id=other_id, status="failed", finished_at=NOW)
        if violation == "submission":
            values.update(submission_id=run.submission_id, status="failed", finished_at=NOW)
    elif violation in ("foreign_attempt", "attempt_budget", "negative_usage"):
        table = "ai_provider_attempts"
        values = asdict(
            ProviderAttempt(
                id=uuid4(),
                user_id=run.user_id,
                run_id=run.id,
                number=1,
                status="started",
                started_at=NOW,
            )
        )
        values.update(user_id=other_id if violation == "foreign_attempt" else run.user_id)
        if violation == "attempt_budget":
            values["number"] = 5
        if violation == "negative_usage":
            values["input_tokens"] = -1
    elif violation in ("foreign_tool", "tool_budget"):
        table = "ai_tool_executions"
        values = asdict(
            ToolExecution(
                id=uuid4(),
                user_id=run.user_id,
                run_id=run.id,
                number=1,
                call_id="call-1",
                tool_name="fake_double",
                status="started",
                started_at=NOW,
            )
        )
        values["user_id"] = other_id if violation == "foreign_tool" else run.user_id
        if violation == "tool_budget":
            values["number"] = 9
    elif violation == "message_sequence":
        values["sequence"] = 1
    elif violation == "message_bytes":
        values["content"] = "я" * 8193
    elif violation == "orphan_checkpoint":
        table = "checkpoints"
        values = {
            "thread_id": str(uuid4()),
            "checkpoint_ns": "",
            "checkpoint_id": "one",
            "checkpoint": {},
        }
    with ai_database.begin() as connection:
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(insert(Base.metadata.tables[table]).values(**values))


def test_failed_message_insert_rolls_back_sequence_and_activity(ai_database: Engine) -> None:
    conversation, _ = seed(ai_database)
    first = make_message(conversation)
    with Session(ai_database) as database, database.begin():
        SqlAlchemyAiRepository(database).append_message(first)
    with Session(ai_database) as database:
        with pytest.raises(IntegrityError), database.begin():
            SqlAlchemyAiRepository(database).append_message(
                replace(first, sequence=2, created_at=NOW + timedelta(seconds=1))
            )
    with Session(ai_database) as database:
        repository = SqlAlchemyAiRepository(database)
        assert repository.get_conversation(conversation.user_id, conversation.id) == replace(
            conversation, next_sequence=2, last_user_message_at=NOW
        )
        assert repository.messages(conversation.user_id, conversation.id, 0, 20) == [first]


def test_checkpoint_content_cascades_but_execution_journal_survives_chat_deletion(
    ai_database: Engine,
) -> None:
    conversation, other_id = seed(ai_database)
    run = make_run(conversation)
    with Session(ai_database) as database, database.begin():
        repository = SqlAlchemyAiRepository(database)
        repository.append_message(make_message(conversation))
        repository.create_run(run)
        repository.create_attempt(
            ProviderAttempt(
                id=uuid4(),
                user_id=run.user_id,
                run_id=run.id,
                number=1,
                status="started",
                started_at=NOW,
            )
        )
        repository.create_tool_execution(
            ToolExecution(
                id=uuid4(),
                user_id=run.user_id,
                run_id=run.id,
                number=1,
                call_id="call-1",
                tool_name="fake_double",
                status="started",
                started_at=NOW,
            )
        )
    with checkpoint_connection(ai_database) as connection:
        saver = OwnedPostgresSaver(connection, conversation.user_id, conversation.id)
        saver.validate_schema()
        saved = save_checkpoint(saver, conversation)
        stored = saver.get_tuple(saved)
        assert stored is not None
        assert (
            stored.checkpoint["channel_values"]["messages"][0].content == "Synthetic private body"
        )
        assert stored.pending_writes == [("task-1", "result", "Synthetic tool result")]
        assert len(list(saver.list(config(conversation)))) == 1
        foreign = OwnedPostgresSaver(connection, other_id, conversation.id)
        for operation in (
            lambda: foreign.get_tuple(saved),
            lambda: list(foreign.list(saved)),
            lambda: save_checkpoint(foreign, conversation),
        ):
            with pytest.raises(AiNotFound):
                operation()
        with ai_database.begin() as database:
            database.execute(
                delete(ConversationModel).where(ConversationModel.id == conversation.id)
            )
        with pytest.raises(AiNotFound):
            saver.get_tuple(saved)
    with Session(ai_database) as database:
        repository = SqlAlchemyAiRepository(database)
        assert repository.get_run(run.user_id, run.id) == replace(run, conversation_id=None)
        assert repository.submission(run.user_id, run.submission_id) is not None
        assert (
            len(repository.attempts(run.user_id, run.id))
            == len(repository.tool_executions(run.user_id, run.id))
            == 1
        )
        assert repository.messages(run.user_id, conversation.id, 0, 20) == []
        for table in (
            checkpoint_schema.checkpoints,
            checkpoint_schema.checkpoint_blobs,
            checkpoint_schema.checkpoint_writes,
        ):
            assert database.scalar(select(func.count()).select_from(table)) == 0
        database.execute(delete(UserModel).where(UserModel.id == run.user_id))
        database.commit()
        assert repository.get_run(run.user_id, run.id) is None
        assert (
            repository.attempts(run.user_id, run.id)
            == repository.tool_executions(run.user_id, run.id)
            == []
        )


@pytest.mark.parametrize(
    "age,last_user_age,disabled,allowed",
    [
        (timedelta(days=30) - timedelta(microseconds=1), None, False, True),
        (timedelta(days=30), None, False, False),
        (timedelta(days=31), None, False, False),
        (timedelta(0), None, True, False),
        (timedelta(days=31), timedelta(days=29), False, True),
        (timedelta(days=31), timedelta(days=30), False, False),
    ],
)
def test_checkpoint_access_checks_exact_expiry_and_active_owner(
    ai_database: Engine,
    age: timedelta,
    last_user_age: timedelta | None,
    disabled: bool,
    allowed: bool,
) -> None:
    conversation, _ = seed(ai_database)
    with ai_database.begin() as database:
        database.execute(
            update(ConversationModel).values(
                created_at=NOW - age,
                last_user_message_at=NOW - last_user_age if last_user_age is not None else None,
            )
        )
        if disabled:
            database.execute(
                update(UserModel)
                .where(UserModel.id == conversation.user_id)
                .values(status="disabled")
            )
    with checkpoint_connection(ai_database) as connection:
        saver = OwnedPostgresSaver(
            connection, conversation.user_id, conversation.id, now=lambda: NOW
        )
        if allowed:
            save_checkpoint(saver, conversation)
        else:
            with pytest.raises(AiNotFound):
                save_checkpoint(saver, conversation)


def test_checkpoint_failed_batch_rolls_back_blobs_and_schema_mismatch_does_not_run_setup(
    ai_database: Engine,
) -> None:
    conversation, _ = seed(ai_database)
    with checkpoint_connection(ai_database) as connection:
        saver = OwnedPostgresSaver(connection, conversation.user_id, conversation.id)
        bad = cast(
            Checkpoint,
            dict(
                empty_checkpoint(),
                id=None,
                channel_values={"value": ["body"]},
                channel_versions={"value": "1"},
            ),
        )
        with pytest.raises(AiPersistenceUnavailable):
            saver.put(config(conversation), bad, {}, {"value": "1"})
        assert connection.execute("SELECT count(*) AS count FROM checkpoint_blobs").fetchone() == {
            "count": 0
        }
        assert saver.get_tuple(config(conversation)) is None
        connection.execute("DELETE FROM checkpoint_migrations WHERE v = 9")
        with pytest.raises(AiPersistenceUnavailable):
            saver.validate_schema()
        assert connection.execute(
            "SELECT max(v) AS version FROM checkpoint_migrations"
        ).fetchone() == {"version": 8}


def test_concurrent_message_admission_accepts_exactly_one_sequence(ai_database: Engine) -> None:
    conversation, _ = seed(ai_database)
    barrier = Barrier(2)
    original = SqlAlchemyAiRepository.get_conversation

    def read(repository, *args):
        current = original(repository, *args)
        barrier.wait(timeout=5)
        return current

    def append() -> bool:
        with Session(ai_database) as database:
            try:
                with database.begin():
                    SqlAlchemyAiRepository(database).append_message(make_message(conversation))
                return True
            except AiConflict:
                return False

    with (
        patch.object(SqlAlchemyAiRepository, "get_conversation", read),
        ThreadPoolExecutor(2) as pool,
    ):
        futures = [pool.submit(append) for _ in range(2)]
        assert sorted(future.result(timeout=10) for future in futures) == [False, True]
    with Session(ai_database) as database:
        assert (
            len(
                SqlAlchemyAiRepository(database).messages(
                    conversation.user_id, conversation.id, 0, 20
                )
            )
            == 1
        )


def test_checkpoint_shared_lock_serializes_concurrent_deletion_and_prevents_recreation(
    ai_database: Engine,
) -> None:
    conversation, _ = seed(ai_database)

    def delete_while_locked() -> bool:
        with checkpoint_connection(ai_database) as other:
            other.execute("SET lock_timeout = '150ms'")
            try:
                other.execute("DELETE FROM ai_conversations WHERE id = %s", (conversation.id,))
            except LockNotAvailable:
                return False
            return True

    with checkpoint_connection(ai_database) as connection:
        saver = OwnedPostgresSaver(connection, conversation.user_id, conversation.id)
        with saver._cursor() as cursor, ThreadPoolExecutor(1) as pool:
            assert pool.submit(delete_while_locked).result(timeout=5) is False
            cursor.execute(
                "INSERT INTO checkpoint_blobs (thread_id, channel, version, type, blob) "
                "VALUES (%s, 'value', '1', 'str', %s)",
                (str(conversation.id), b"body"),
            )
        assert delete_while_locked()
        with pytest.raises(AiNotFound):
            save_checkpoint(saver, conversation)
        assert connection.execute("SELECT count(*) AS count FROM checkpoint_blobs").fetchone() == {
            "count": 0
        }


def test_concurrent_run_admission_accepts_only_one_active_run(ai_database: Engine) -> None:
    conversation, _ = seed(ai_database)
    barrier = Barrier(2)

    def admit() -> bool:
        with Session(ai_database) as database:
            barrier.wait(timeout=5)
            try:
                with database.begin():
                    SqlAlchemyAiRepository(database).create_run(make_run(conversation))
                return True
            except IntegrityError:
                return False

    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(admit) for _ in range(2)]
        assert sorted(future.result(timeout=10) for future in futures) == [False, True]
    with Session(ai_database) as database:
        assert database.scalar(select(func.count()).select_from(RunModel)) == 1


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_owned_agent_resumes_in_fresh_process_without_replaying_review(
    ai_database: Engine, decision: str
) -> None:
    conversation, other_id = seed(ai_database)
    data = {
        "schema": ai_database.dialect.default_schema_name,
        "user_id": str(conversation.user_id),
        "conversation_id": str(conversation.id),
        "phase": "start",
    }

    def process(payload: dict) -> dict:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("ai_checkpoint_process.py"))],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=30,
            env=os.environ
            | {
                "AI_CHECKPOINT_PROCESS_DSN": ai_database.url.set(
                    drivername="postgresql"
                ).render_as_string(hide_password=False),
                "LANGSMITH_TRACING": "false",
                "LANGCHAIN_TRACING_V2": "false",
            },
        )
        assert result.returncode == 0, result.stderr
        output = json.loads(result.stdout)
        assert output.get("result", {}).get("status") != "failed", result.stderr
        return output

    pending = process(data)
    assert pending["result"]["status"] == "interrupted" and pending["tool_calls"] == 0
    review = {"interrupt_id": pending["result"]["review"]["interrupt_id"], "decisions": [decision]}
    resume = data | {"phase": "resume", "review": review}
    assert process(resume | {"user_id": str(other_id)}) == {"denied": True, "tool_calls": 0}
    resumed = process(resume)
    assert resumed["result"]["status"] == "completed"
    assert resumed["result"]["answer"] == "Finished"
    assert resumed["result"]["tools"][0]["status"] == (
        "success" if decision == "approve" else "error"
    )
    assert resumed["tool_calls"] == (1 if decision == "approve" else 0)
    assert process(resume) == {"stale": True, "tool_calls": 0}
    with ai_database.begin() as connection:
        connection.execute(delete(ConversationModel).where(ConversationModel.id == conversation.id))
    assert process(resume) == {"denied": True, "tool_calls": 0}
