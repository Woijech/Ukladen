import socket
from typing import cast
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langsmith import Client
from pydantic import ValidationError

from app.integrations.llm.fake import FakeChatModel
from app.modules.ai.application.agent import (
    AgentInput,
    AgentReview,
    AgentRunner,
    InvalidAgentReview,
)
from app.modules.ai.infrastructure.agent import OfflineAgentRunner
from app.modules.ai.infrastructure.fake_tools import fake_double, fake_reviewed_double

double_tool = cast(StructuredTool, fake_double)
reviewed_tool = cast(StructuredTool, fake_reviewed_double)


@pytest.fixture(autouse=True)
def offline_only(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args, **kwargs):
        pytest.fail("Offline agent attempted network access.")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


def tool_message(
    name: str = "fake_double", value: object = 7, call_id: str = "call-1"
) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": name,
                "args": {"value": value},
                "id": call_id,
                "type": "tool_call",
            }
        ],
    )


def runner(*responses: AIMessage, **kwargs) -> OfflineAgentRunner:
    return OfflineAgentRunner(
        FakeChatModel(responses=responses),
        [fake_double, fake_reviewed_double],
        InMemorySaver(serde=JsonPlusSerializer(pickle_fallback=False, allowed_msgpack_modules=[])),
        review_tools=frozenset({"fake_reviewed_double"}),
        **kwargs,
    )


def request(conversation_id: UUID | None = None) -> AgentInput:
    return AgentInput(conversation_id=conversation_id or uuid4(), message="Synthetic test")


def test_typed_tool_exchange_and_neutral_result() -> None:
    agent: AgentRunner = runner(tool_message(), AIMessage(content="Done"))
    result = agent.run(request())
    assert result.status == "completed" and result.answer == "Done"
    assert result.review is None
    assert len(result.tools) == 1
    assert result.tools[0].model_dump() == {
        "call_id": "call-1",
        "tool_name": "fake_double",
        "status": "success",
        "content": '{"value": 14}',
    }


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_pause_and_resume_in_new_runner_uses_checkpoint(decision: str) -> None:
    model = FakeChatModel(
        responses=(
            tool_message("fake_reviewed_double"),
            AIMessage(content="Finished"),
        )
    )
    checkpoints = InMemorySaver(
        serde=JsonPlusSerializer(pickle_fallback=False, allowed_msgpack_modules=[])
    )

    def build() -> OfflineAgentRunner:
        return OfflineAgentRunner(
            model,
            [fake_reviewed_double],
            checkpoints,
            review_tools=frozenset({"fake_reviewed_double"}),
        )

    start = request()
    with patch.object(reviewed_tool, "func", wraps=reviewed_tool.func) as operation:
        pending = build().run(start)
        assert pending.status == "interrupted" and pending.review is not None
        assert pending.review.actions[0].model_dump() == {
            "tool_name": "fake_reviewed_double",
            "arguments": {"value": 7},
        }
        operation.assert_not_called()
        review = AgentReview.model_validate(
            {
                "interrupt_id": pending.review.interrupt_id,
                "decisions": [decision],
            }
        )
        resumed = build().resume(start.conversation_id, review)
        assert resumed.status == "completed" and resumed.answer == "Finished"
        assert resumed.tools[0].status == ("success" if decision == "approve" else "error")
        assert operation.call_count == (1 if decision == "approve" else 0)
        with pytest.raises(InvalidAgentReview):
            build().resume(start.conversation_id, review)
        assert operation.call_count == (1 if decision == "approve" else 0)


def test_pending_review_rejects_new_message_wrong_thread_stale_id_and_partial_batch() -> None:
    calls = tool_message("fake_reviewed_double")
    calls.tool_calls.append(
        {
            "name": "fake_reviewed_double",
            "args": {"value": 8},
            "id": "call-2",
            "type": "tool_call",
        }
    )
    agent = runner(calls, AIMessage(content="Done"))
    start = request()
    with patch.object(reviewed_tool, "func", wraps=reviewed_tool.func) as operation:
        pending = agent.run(start)
        assert pending.review is not None and len(pending.review.actions) == 2
        review = AgentReview(
            interrupt_id=pending.review.interrupt_id, decisions=("approve", "reject")
        )
        with pytest.raises(InvalidAgentReview):
            agent.run(start)
        with pytest.raises(InvalidAgentReview):
            agent.resume(uuid4(), review)
        with pytest.raises(InvalidAgentReview):
            agent.resume(start.conversation_id, review.model_copy(update={"interrupt_id": "stale"}))
        with pytest.raises(InvalidAgentReview):
            agent.resume(
                start.conversation_id,
                AgentReview(
                    interrupt_id=review.interrupt_id,
                    decisions=("approve",),
                ),
            )
        operation.assert_not_called()
        assert agent.resume(start.conversation_id, review).status == "completed"
        operation.assert_called_once_with(value=7)


@pytest.mark.parametrize("value", ["7", True, None, -1, 101, {"private": "body"}])
def test_invalid_tool_arguments_are_not_executed_or_exposed(value: object) -> None:
    agent = runner(tool_message(value=value), AIMessage(content="Cannot perform tool"))
    with patch.object(double_tool, "func", wraps=double_tool.func) as operation:
        result = agent.run(request())
        operation.assert_not_called()
    assert result.tools[0].status == "error"
    assert result.tools[0].content == "Tool unavailable or invalid input."
    assert "private" not in result.model_dump_json()


def test_unknown_tool_and_extra_arguments_are_rejected() -> None:
    for message in (tool_message("unregistered"), tool_message()):
        if message.tool_calls[0]["name"] == "fake_double":
            message.tool_calls[0]["args"]["owner_id"] = "forged"
        with patch.object(double_tool, "func", wraps=double_tool.func) as operation:
            result = runner(message, AIMessage(content="Unavailable")).run(request())
            operation.assert_not_called()
        assert result.tools[0].status == "error"
        assert result.tools[0].content == "Tool unavailable or invalid input."


def test_tool_exception_is_sanitized_without_retry() -> None:
    with patch.object(
        fake_double, "func", side_effect=RuntimeError("private-response")
    ) as operation:
        result = runner(tool_message(), AIMessage(content="Unavailable")).run(request())
    operation.assert_called_once_with(value=7)
    assert result.tools[0].status == "error"
    assert "private-response" not in result.model_dump_json()


def test_model_and_tool_limits_bound_actual_invocations() -> None:
    responses = (
        tool_message(call_id="call-1"),
        tool_message(call_id="call-2"),
        tool_message(call_id="call-3"),
        AIMessage(content="Done"),
    )
    with patch.object(double_tool, "func", wraps=double_tool.func) as operation:
        assert runner(*responses, model_limit=2).run(request()).status == "limited"
        assert operation.call_count == 2
    with patch.object(double_tool, "func", wraps=double_tool.func) as operation:
        assert runner(*responses, tool_limit=1).run(request()).status == "limited"
        assert operation.call_count == 1


def test_oversized_tool_result_is_not_forwarded_and_answer_is_bounded() -> None:
    with patch.object(fake_double, "func", return_value="private-" + "x" * 16384):
        result = runner(tool_message(), AIMessage(content="Unavailable")).run(request())
    assert result.tools[0].status == "error" and "private-" not in result.model_dump_json()
    assert runner(AIMessage(content="я" * 8193)).run(request()).status == "limited"


def test_review_batch_is_bounded_before_any_tool_executes() -> None:
    message = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "fake_reviewed_double",
                "args": {"value": 7},
                "id": f"call-{index}",
                "type": "tool_call",
            }
            for index in range(9)
        ],
    )
    with patch.object(reviewed_tool, "func", wraps=reviewed_tool.func) as operation:
        assert runner(message).run(request()).status == "limited"
        operation.assert_not_called()


def test_fake_failure_does_not_escape_and_unknown_usage_is_not_fabricated() -> None:
    result = runner(tool_message()).run(request())
    assert result.status == "failed" and result.answer is None
    assert FakeChatModel(responses=(AIMessage(content="Done"),)).responses[0].usage_metadata is None


def test_fake_scripts_restart_for_new_user_turn_without_mutating_script() -> None:
    responses = (tool_message(), AIMessage(content="Done"))
    agent = runner(*responses)
    start = request()
    assert agent.run(start).status == "completed"
    assert len(agent.run(start).tools) == 1
    assert responses[0].id is None and responses[1].id is None
    assert agent.run(request()).status == "completed"


def test_external_tracing_stays_disabled_even_when_environment_enables_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "synthetic-only")
    send = Mock(side_effect=AssertionError("Tracing must stay disabled"))
    monkeypatch.setattr(Client, "create_run", send)
    assert runner(AIMessage(content="Synthetic")).run(request()).status == "completed"
    send.assert_not_called()


@pytest.mark.parametrize("message", ["", "  ", "я" * 8193, "\ud800"])
def test_user_message_utf8_limits(message: str) -> None:
    with pytest.raises(ValidationError):
        AgentInput(conversation_id=uuid4(), message=message)
    assert AgentInput(conversation_id=uuid4(), message="я" * 8192)


@pytest.mark.parametrize(
    "changes",
    [
        {"decisions": ["edit"]},
        {"decisions": []},
        {"arguments": {"value": 9}},
    ],
)
def test_reviews_cannot_edit_arguments_or_omit_decisions(changes: dict) -> None:
    with pytest.raises(ValidationError):
        AgentReview.model_validate({"interrupt_id": "test", "decisions": ["approve"]} | changes)


def test_invalid_registration_and_limits_are_rejected_before_execution() -> None:
    for kwargs in ({"model_limit": 0}, {"tool_limit": 9}, {"model_limit": 5}, {"tool_limit": True}):
        with pytest.raises(ValueError):
            runner(AIMessage(content="Done"), **kwargs)
    with pytest.raises(ValueError):
        OfflineAgentRunner(
            FakeChatModel(responses=(AIMessage(content="Done"),)),
            [fake_double, fake_double],
            InMemorySaver(),
        )
    with pytest.raises(ValueError):
        OfflineAgentRunner(
            FakeChatModel(responses=(AIMessage(content="Done"),)),
            [],
            InMemorySaver(),
            review_tools=frozenset({"missing"}),
        )
