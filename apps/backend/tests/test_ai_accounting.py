from typing import cast
from unittest.mock import create_autospec, patch
from uuid import uuid4

import pytest
from langchain.agents.middleware import ToolCallRequest
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver
from test_ai_agent import offline_only as offline_only
from test_ai_agent import tool_message

from app.integrations.llm.fake import FakeChatModel
from app.modules.ai.application.agent import AgentInput
from app.modules.ai.application.lifecycle import ExecutionJournal
from app.modules.ai.domain.state import InvalidAiState
from app.modules.ai.infrastructure.accounting import AccountingMiddleware
from app.modules.ai.infrastructure.agent import OfflineAgentRunner
from app.modules.ai.infrastructure.fake_tools import fake_double


@pytest.mark.parametrize("limit", [1, 4])
def test_journal_counts_only_dispatched_model_and_tool_calls(limit: int) -> None:
    journal = create_autospec(ExecutionJournal, instance=True)
    runner = OfflineAgentRunner(
        FakeChatModel(responses=(tool_message(), AIMessage(content="Done"))),
        [fake_double],
        InMemorySaver(),
        journal=journal,
        model_limit=limit,
    )
    result = runner.run(AgentInput(conversation_id=uuid4(), message="Test"))
    assert result.status == ("limited" if limit == 1 else "completed")
    assert (
        journal.start_attempt.call_count
        == journal.finish_attempt.call_count
        == (1 if limit == 1 else 2)
    )
    assert journal.start_tool.call_count == journal.finish_tool.call_count == 1
    assert journal.finish_attempt.call_args.kwargs == {"input_tokens": None, "output_tokens": None}


def test_actual_usage_and_tool_error_outcomes_are_recorded_without_content() -> None:
    journal = create_autospec(ExecutionJournal, instance=True)
    model = FakeChatModel(
        responses=(
            tool_message(),
            AIMessage(
                content="Done",
                usage_metadata={"input_tokens": 12, "output_tokens": 0, "total_tokens": 12},
            ),
        )
    )
    runner = OfflineAgentRunner(model, [fake_double], InMemorySaver(), journal=journal)
    with patch.object(
        cast(StructuredTool, fake_double), "func", side_effect=RuntimeError("private-body")
    ):
        assert runner.run(AgentInput(conversation_id=uuid4(), message="Test")).status == "completed"
    assert journal.finish_attempt.call_args.kwargs == {"input_tokens": 12, "output_tokens": 0}
    assert journal.finish_tool.call_args.args[1:] == ("failed", "invalid_response")
    assert "private-body" not in str(journal.mock_calls)


def test_missing_tool_call_id_is_rejected_before_dispatch() -> None:
    journal = create_autospec(ExecutionJournal, instance=True)
    request = create_autospec(ToolCallRequest, instance=True)
    request.tool_call = {"id": None, "name": "fake_double"}
    handler = create_autospec(lambda request: None)
    with pytest.raises(InvalidAiState):
        AccountingMiddleware(journal).wrap_tool_call(request, handler)
    journal.start_tool.assert_not_called()
    handler.assert_not_called()
