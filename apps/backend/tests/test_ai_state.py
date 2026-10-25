from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import create_autospec
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.modules.ai.application.persistence import AiRepository
from app.modules.ai.domain.state import (
    AiConflict,
    AiNotFound,
    Conversation,
    InvalidAiState,
    Message,
    ProviderAttempt,
    Run,
    ToolExecution,
)
from app.modules.ai.infrastructure.orm import ConversationModel
from app.modules.ai.infrastructure.repository import SqlAlchemyAiRepository

NOW = datetime(2026, 10, 22, 9, tzinfo=UTC)


def make_run() -> Run:
    return Run(
        id=uuid4(),
        user_id=uuid4(),
        conversation_id=uuid4(),
        submission_id=uuid4(),
        request_digest="a" * 64,
        provider="fake",
        model="fake-v1",
        status="queued",
        created_at=NOW,
        updated_at=NOW,
    )


def test_run_transitions_are_versioned_and_terminal_states_cannot_reopen() -> None:
    queued = make_run()
    running = queued.transition("running", NOW + timedelta(seconds=1))
    interrupted = running.transition("interrupted", NOW + timedelta(seconds=2))
    resumed = interrupted.transition("running", NOW + timedelta(seconds=3))
    completed = resumed.transition("completed", NOW + timedelta(seconds=4))
    assert (
        queued.version,
        running.version,
        interrupted.version,
        resumed.version,
        completed.version,
    ) == (1, 2, 3, 4, 5)
    assert completed.finished_at == completed.updated_at and interrupted.finished_at is None
    assert completed.transition("completed", NOW + timedelta(seconds=5)) is completed
    with pytest.raises(AiConflict):
        completed.transition("running", NOW + timedelta(seconds=5))
    with pytest.raises(AiConflict):
        queued.transition("completed", NOW)
    with pytest.raises(AiConflict):
        running.transition("failed", NOW)


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "invalid"},
        {"request_digest": "private text"},
        {"provider": "unsafe key value"},
        {"version": 0},
        {"updated_at": NOW - timedelta(seconds=1)},
        {"finished_at": NOW},
        {"created_at": NOW.replace(tzinfo=None)},
    ],
)
def test_invalid_run_metadata_is_rejected(changes: dict) -> None:
    with pytest.raises(InvalidAiState):
        replace(make_run(), **changes)


def test_unknown_usage_is_distinct_from_known_zero_and_metadata_excludes_content() -> None:
    attempt = ProviderAttempt(
        id=uuid4(), user_id=uuid4(), run_id=uuid4(), number=1, status="started", started_at=NOW
    )
    finished = replace(attempt, status="succeeded", finished_at=NOW)
    assert finished.input_tokens is None and finished.output_tokens is None
    known_zero = replace(finished, input_tokens=0, output_tokens=0)
    assert known_zero.input_tokens == known_zero.output_tokens == 0
    partial = replace(finished, input_tokens=12)
    assert partial.input_tokens == 12 and partial.output_tokens is None
    for changes in (
        {"input_tokens": -1},
        {"output_tokens": True},
        {"number": 0},
        {"error_code": "private exception"},
        {"error_code": "timeout"},
        {"finished_at": NOW - timedelta(seconds=1)},
    ):
        with pytest.raises(InvalidAiState):
            replace(finished, **changes)
    assert set(attempt.__dataclass_fields__).isdisjoint(
        {"prompt", "content", "api_key", "metadata"}
    )
    assert "a" * 64 not in repr(make_run())


def test_content_representation_and_utf8_limits() -> None:
    user_id, conversation_id = uuid4(), uuid4()
    conversation = Conversation(
        id=conversation_id, user_id=user_id, title="private-title", created_at=NOW
    )
    message = Message(
        id=uuid4(),
        user_id=user_id,
        conversation_id=conversation_id,
        sequence=1,
        role="user",
        content="private-body",
        created_at=NOW,
    )
    assert "private-title" not in repr(conversation) and "private-body" not in repr(message)
    assert replace(message, content="я" * 8192)
    for changes in (
        {"content": "я" * 8193},
        {"sequence": 0},
        {"role": "system"},
        {"content": "\ud800"},
        {"created_at": NOW.replace(tzinfo=None)},
    ):
        with pytest.raises(InvalidAiState):
            replace(message, **changes)


def test_tool_outcome_categories_cannot_store_exception_text() -> None:
    execution = ToolExecution(
        id=uuid4(),
        user_id=uuid4(),
        run_id=uuid4(),
        number=1,
        call_id="call-1",
        tool_name="fake_double",
        status="started",
        started_at=NOW,
    )
    assert replace(execution, status="rejected", finished_at=NOW)
    for changes in (
        {"number": 9},
        {"tool_name": "tool with secret"},
        {"status": "failed"},
        {"error_code": "private-error"},
    ):
        with pytest.raises(InvalidAiState):
            replace(execution, **changes)


def test_append_uses_sequence_compare_and_swap_and_only_user_messages_renew_activity() -> None:
    run = make_run()
    database = create_autospec(Session, instance=True)
    repository: AiRepository = SqlAlchemyAiRepository(database)
    for role in ("user", "assistant", "tool"):
        database.reset_mock()
        database.scalar.side_effect = [
            ConversationModel(
                id=run.conversation_id,
                user_id=run.user_id,
                title="Test",
                created_at=NOW,
                last_user_message_at=None,
                next_sequence=1,
                provider="fake",
                model="fake-v1",
            ),
            run.conversation_id,
        ]
        assert run.conversation_id is not None
        message = Message(
            id=uuid4(),
            user_id=run.user_id,
            conversation_id=run.conversation_id,
            sequence=1,
            role=role,
            content="Body",
            created_at=NOW,
        )
        repository.append_message(message)
        update = database.scalar.call_args.args[0].compile(dialect=postgresql.dialect())
        assert "ai_conversations.next_sequence =" in str(update)
        assert (
            run.user_id in update.params.values() and run.conversation_id in update.params.values()
        )
        assert ("last_user_message_at" in str(update)) == (role == "user")
        database.add.assert_called_once()
        database.flush.assert_called_once()


@pytest.mark.parametrize("missing", [True, False])
def test_append_missing_or_stale_conversation_does_not_add_content(missing: bool) -> None:
    database = create_autospec(Session, instance=True)
    repository = SqlAlchemyAiRepository(database)
    user_id, conversation_id = uuid4(), uuid4()
    database.scalar.side_effect = (
        [None]
        if missing
        else [
            ConversationModel(
                id=conversation_id,
                user_id=user_id,
                title="Test",
                created_at=NOW,
                last_user_message_at=None,
                next_sequence=2,
                provider="fake",
                model="fake-v1",
            ),
            None,
        ]
    )
    with pytest.raises(AiNotFound if missing else AiConflict):
        repository.append_message(
            Message(
                id=uuid4(),
                user_id=user_id,
                conversation_id=conversation_id,
                sequence=1,
                role="user",
                content="Body",
                created_at=NOW,
            )
        )
    database.add.assert_not_called()


def test_foreign_run_creation_and_terminal_reopen_are_rejected_before_insert() -> None:
    database = create_autospec(Session, instance=True)
    database.scalar.return_value = None
    repository = SqlAlchemyAiRepository(database)
    run = make_run()
    with pytest.raises(AiNotFound):
        repository.create_run(run)
    database.add.assert_not_called()
    complete = run.transition("running", NOW).transition("completed", NOW)
    with pytest.raises(AiConflict):
        repository.save_run(run, "completed")
    database.reset_mock()
    database.scalar.return_value = run.id
    repository.save_run(complete, "running")
    statement = database.scalar.call_args.args[0].compile(dialect=postgresql.dialect())
    assert "ai_runs.version =" in str(statement)
    assert complete.version - 1 in statement.params.values()


def test_owner_read_filters_and_bounded_message_order() -> None:
    database = create_autospec(Session, instance=True)
    database.scalar.return_value = None
    database.scalars.return_value = []
    repository = SqlAlchemyAiRepository(database)
    user_id, identifier = uuid4(), uuid4()
    for method in (repository.get_conversation, repository.get_run, repository.submission):
        assert method(user_id, identifier) is None
        params = database.scalar.call_args.args[0].compile().params.values()
        assert user_id in params and identifier in params
    assert repository.messages(user_id, identifier, 7, 20) == []
    statement = database.scalars.call_args.args[0].compile(dialect=postgresql.dialect())
    assert "ORDER BY ai_messages.sequence" in str(statement)
    assert user_id in statement.params.values() and identifier in statement.params.values()
    assert 7 in statement.params.values() and 20 in statement.params.values()
    with pytest.raises(InvalidAiState):
        repository.messages(user_id, identifier, -1, 20)
    with pytest.raises(InvalidAiState):
        repository.list_conversations(user_id, 201, 0)


def test_attempt_and_tool_outcomes_can_only_complete_started_records() -> None:
    database = create_autospec(Session, instance=True)
    database.scalar.return_value = None
    repository = SqlAlchemyAiRepository(database)
    attempt = ProviderAttempt(
        id=uuid4(), user_id=uuid4(), run_id=uuid4(), number=1, status="started", started_at=NOW
    )
    tool = ToolExecution(
        id=uuid4(),
        user_id=attempt.user_id,
        run_id=attempt.run_id,
        number=1,
        call_id="call-1",
        tool_name="fake_double",
        status="started",
        started_at=NOW,
    )
    repository.create_attempt(attempt)
    repository.create_tool_execution(tool)
    with pytest.raises(InvalidAiState):
        repository.save_attempt(attempt)
    with pytest.raises(InvalidAiState):
        repository.save_tool_execution(tool)
    with pytest.raises(AiConflict):
        repository.save_attempt(replace(attempt, status="succeeded", finished_at=NOW))
    with pytest.raises(AiConflict):
        repository.save_tool_execution(replace(tool, status="succeeded", finished_at=NOW))
    for call in database.scalar.call_args_list:
        query = call.args[0].compile()
        assert "started" in query.params.values() and attempt.user_id in query.params.values()
