from collections.abc import Callable
from typing import Any

from langchain.agents.middleware import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
)
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command

from app.modules.ai.application.lifecycle import ExecutionJournal
from app.modules.ai.domain.state import InvalidAiState


class AccountingMiddleware(AgentMiddleware):
    def __init__(self, journal: ExecutionJournal) -> None:
        self.journal = journal

    def wrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]
    ) -> ModelResponse:
        attempt = self.journal.start_attempt()
        try:
            response = handler(request)
        except Exception as error:
            self.journal.finish_attempt(
                attempt,
                "failed",
                error="timeout" if isinstance(error, TimeoutError) else "unavailable",
            )
            raise
        usage = next(
            (
                message.usage_metadata
                for message in response.result
                if isinstance(message, AIMessage)
            ),
            None,
        )
        self.journal.finish_attempt(
            attempt,
            "succeeded",
            input_tokens=usage.get("input_tokens") if usage else None,
            output_tokens=usage.get("output_tokens") if usage else None,
        )
        self.journal.check()
        return response

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        call_id = request.tool_call.get("id")
        if call_id is None:
            raise InvalidAiState("A tool call identifier is required.")
        tool = self.journal.start_tool(call_id, request.tool_call["name"])
        try:
            response = handler(request)
        except Exception as error:
            self.journal.finish_tool(
                tool, "failed", "timeout" if isinstance(error, TimeoutError) else "unavailable"
            )
            raise
        failed = isinstance(response, ToolMessage) and response.status == "error"
        self.journal.finish_tool(
            tool, "failed" if failed else "succeeded", "invalid_response" if failed else None
        )
        self.journal.check()
        return response
