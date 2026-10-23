from threading import BoundedSemaphore, Event
from time import monotonic
from typing import cast
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool
from test_ai_agent import offline_only as offline_only
from test_ai_agent import request, runner, tool_message

from app.integrations.llm.fake import FakeChatModel
from app.modules.ai.infrastructure import bounds
from app.modules.ai.infrastructure.fake_tools import fake_double


@pytest.mark.parametrize(
    "error, expected", [(ConnectionError, 2), (ValueError, 1), (TimeoutError, 1)]
)
def test_only_connection_errors_retry_once(error: type[Exception], expected: int) -> None:
    with patch.object(FakeChatModel, "_generate", side_effect=error("private body")) as provider:
        result = runner(AIMessage(content="Unused")).run(request())
    assert result.status == "failed" and provider.call_count == expected
    assert "private" not in result.model_dump_json()


def test_transient_retry_and_total_attempt_budget_include_retries() -> None:
    original = FakeChatModel._generate
    calls = 0

    def transient(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls % 2:
            raise ConnectionError("private body")
        return original(self, *args, **kwargs)

    with patch.object(FakeChatModel, "_generate", transient):
        result = runner(AIMessage(content="Done")).run(request())
    assert result.status == "completed" and calls == 2
    calls = 0
    with patch.object(FakeChatModel, "_generate", transient):
        limited = runner(
            tool_message(call_id="one"), tool_message(call_id="two"), AIMessage(content="Unused")
        ).run(request())
    assert limited.status == "limited" and calls == 4


@pytest.mark.parametrize("target", ["model", "tool"])
def test_deadline_returns_before_blocked_handler_and_discards_late_result(target: str) -> None:
    entered, release, finished = Event(), Event(), Event()
    model = target == "model"
    tool = cast(StructuredTool, fake_double)
    original = FakeChatModel._generate if model else tool.func

    def blocked(*args, **kwargs):
        entered.set()
        try:
            assert release.wait(5)
            assert original is not None
            return original(*args, **kwargs)
        finally:
            finished.set()

    agent = runner(
        tool_message(), AIMessage(content="Late"), run_timeout=0.2 if model else 2, tool_timeout=0.1
    )
    start = request()
    with patch.object(FakeChatModel if model else tool, "_generate" if model else "func", blocked):
        try:
            before = monotonic()
            result = agent.run(start)
            assert entered.is_set() and not finished.is_set()
            assert result.status == "failed" and result.error_code == "timeout"
            assert monotonic() - before < 1.5
        finally:
            release.set()
            assert finished.wait(5)
    state = agent.graph.get_state(agent._config(start.conversation_id))
    assert not any(message.content == "Late" for message in state.values.get("messages", []))


def test_saturation_rejects_without_dispatch_or_unbounded_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slots = BoundedSemaphore(1)
    monkeypatch.setattr(bounds, "_slots", slots)
    assert slots.acquire(blocking=False)
    try:
        with patch.object(FakeChatModel, "_generate") as provider:
            assert runner(AIMessage(content="Unused")).run(request()).status == "failed"
            provider.assert_not_called()
    finally:
        slots.release()


@pytest.mark.parametrize(
    "field,value",
    [("run_timeout", 0), ("run_timeout", 61), ("run_timeout", float("nan")), ("tool_timeout", 11)],
)
def test_execution_bounds_cannot_be_disabled(field: str, value: float) -> None:
    with pytest.raises(ValueError):
        runner(AIMessage(content="Unused"), **{field: value})
