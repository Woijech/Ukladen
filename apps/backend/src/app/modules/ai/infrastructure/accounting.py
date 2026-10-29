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

from app.modules.ai.application.agent import ProviderFailure
from app.modules.ai.application.diagnostics import record
from app.modules.ai.application.lifecycle import ExecutionJournal
from app.modules.ai.domain.state import InvalidAiState


class AccountingMiddleware(AgentMiddleware):
    def __init__(self, journal: ExecutionJournal) -> None:
        self.journal = journal

    def wrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]
    ) -> ModelResponse:
        attempt = self.journal.start_attempt()
        record(
            "model_request",
            {
                "attempt": attempt.number,
                "messages": [
                    {"role": item.type, "content": item.content} for item in request.messages
                ],
                "system": request.system_message.content if request.system_message else None,
                "tools": [item if isinstance(item, dict) else item.name for item in request.tools],
            },
        )
        try:
            response = handler(request)
        except Exception as error:
            record(
                "model_failure",
                {
                    "attempt": attempt.number,
                    "error_type": type(error).__name__,
                    "error_code": error.error_code
                    if isinstance(error, ProviderFailure)
                    else "unavailable",
                },
            )
            self.journal.finish_attempt(
                attempt,
                "failed",
                error=(
                    error.error_code
                    if isinstance(error, ProviderFailure)
                    else "timeout"
                    if isinstance(error, TimeoutError)
                    else "unavailable"
                ),
                input_tokens=error.input_tokens if isinstance(error, ProviderFailure) else None,
                output_tokens=error.output_tokens if isinstance(error, ProviderFailure) else None,
            )
            raise
        record(
            "model_response",
            {
                "attempt": attempt.number,
                "messages": [
                    {
                        "role": item.type,
                        "content": item.content,
                        "tool_calls": item.tool_calls if isinstance(item, AIMessage) else [],
                    }
                    for item in response.result
                ],
            },
        )
        reported = next(
            (
                message.response_metadata["ukladen_usage"]
                for message in response.result
                if isinstance(message, AIMessage) and "ukladen_usage" in message.response_metadata
            ),
            None,
        )
        usage = (
            reported
            if reported is not None
            else next(
                (
                    message.usage_metadata
                    for message in response.result
                    if isinstance(message, AIMessage)
                ),
                None,
            )
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
        record(
            "tool_request",
            {
                "number": tool.number,
                "name": tool.tool_name,
                "arguments": request.tool_call.get("args"),
            },
        )
        try:
            response = handler(request)
        except Exception as error:
            record("tool_failure", {"number": tool.number, "error_type": type(error).__name__})
            self.journal.finish_tool(
                tool, "failed", "timeout" if isinstance(error, TimeoutError) else "unavailable"
            )
            raise
        record(
            "tool_response",
            {
                "number": tool.number,
                "name": tool.tool_name,
                "content": response.content
                if isinstance(response, ToolMessage)
                else "Application command; inspect proposals in chat.",
            },
        )
        failed = isinstance(response, ToolMessage) and response.status == "error"
        self.journal.finish_tool(
            tool, "failed" if failed else "succeeded", "invalid_response" if failed else None
        )
        self.journal.check()
        return response
