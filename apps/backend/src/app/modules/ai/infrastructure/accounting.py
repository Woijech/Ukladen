import json
from collections.abc import Callable
from typing import Any

from langchain.agents.middleware import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
    wrap_model_call,
)
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.types import Command

from app.modules.ai.application.agent import ProviderFailure
from app.modules.ai.application.diagnostics import attempt_number, capture, record
from app.modules.ai.application.lifecycle import ExecutionJournal
from app.modules.ai.domain.state import InvalidAiState


def content_size(value: Any) -> dict[str, int]:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    return {"characters": len(text), "bytes": len(text.encode("utf-8"))}


@wrap_model_call
def capture_model_input(
    request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]
) -> ModelResponse:
    if capture.get() is not None:
        schemas = [convert_to_openai_tool(tool) for tool in request.tools]
        messages = [
            {"role": item.type, "content": item.content}
            | ({"tool_calls": item.tool_calls} if isinstance(item, AIMessage) else {})
            | (
                {"name": item.name, "tool_call_id": item.tool_call_id}
                if isinstance(item, ToolMessage)
                else {}
            )
            for item in request.messages
        ]
        last_user = max(
            (i for i, item in enumerate(request.messages) if isinstance(item, HumanMessage)),
            default=len(messages),
        )
        parts: dict[str, Any] = {
            "system": request.system_message.content if request.system_message else "",
            "tool_schemas": schemas,
            "history": messages[:last_user],
            "current_request": messages[last_user : last_user + 1],
            "tool_results": [m for m in messages[last_user + 1 :] if m["role"] == "tool"],
            "assistant_calls": [m for m in messages[last_user + 1 :] if m["role"] != "tool"],
        }
        record(
            "model_input",
            {
                "attempt": attempt_number.get(),
                "measurement": "serialized_characters_and_utf8_bytes_not_tokens",
                "parts": {name: content_size(value) for name, value in parts.items()},
                "tools": [
                    {"name": schema["function"]["name"], **content_size(schema)}
                    for schema in schemas
                ],
                "message_count": len(messages),
                "tool_mode": "calendar_lookup"
                if "Tool mode: calendar_lookup." in str(parts["system"])
                else "general",
            },
        )
        record(
            "model_request",
            {
                "attempt": attempt_number.get(),
                "messages": messages,
                "system": parts["system"],
                "tools": [schema["function"]["name"] for schema in schemas],
            },
        )
    return handler(request)


class AccountingMiddleware(AgentMiddleware):
    def __init__(self, journal: ExecutionJournal) -> None:
        self.journal = journal

    def wrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]
    ) -> ModelResponse:
        attempt = self.journal.start_attempt()
        token = attempt_number.set(attempt.number)
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
        finally:
            attempt_number.reset(token)
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
        record("model_usage", {"attempt": attempt.number, "usage": usage})
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
                "call_id": call_id,
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
                "size": content_size(response.content)
                if isinstance(response, ToolMessage) and capture.get() is not None
                else None,
            },
        )
        failed = isinstance(response, ToolMessage) and response.status == "error"
        self.journal.finish_tool(
            tool, "failed" if failed else "succeeded", "invalid_response" if failed else None
        )
        self.journal.check()
        return response
