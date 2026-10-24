import json
import logging
import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any
from uuid import UUID

from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    HumanInTheLoopMiddleware,
    ModelCallLimitMiddleware,
    ModelRetryMiddleware,
    ToolCallLimitMiddleware,
    ToolCallRequest,
    ToolErrorMiddleware,
    wrap_tool_call,
)
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain.agents.middleware.tool_call_limit import ToolCallLimitExceededError
from langchain.agents.middleware.types import InputAgentState
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command
from langsmith import tracing_context

from app.core.logging import log_failure
from app.modules.ai.application.agent import (
    AgentInput,
    AgentResult,
    AgentReview,
    InvalidAgentReview,
    PendingReview,
    ReviewAction,
    ToolOutcome,
)
from app.modules.ai.application.lifecycle import ExecutionJournal
from app.modules.ai.application.streaming import emit, stream_sink
from app.modules.ai.infrastructure.accounting import AccountingMiddleware
from app.modules.ai.infrastructure.bounds import BoundedCalls
from app.modules.ai.infrastructure.grounding import SourceTools
from app.modules.ai.infrastructure.instructions import AssistantInstructions

CALL_LIMIT_ERRORS = (ModelCallLimitExceededError, ToolCallLimitExceededError)
TOOL_ERROR = "Tool unavailable or invalid input."
RESULT_BYTES = 16384
logger = logging.getLogger(__name__)


def tool_error(error: Exception, request: ToolCallRequest) -> str | None:
    return None if isinstance(error, (*CALL_LIMIT_ERRORS, TimeoutError)) else TOOL_ERROR


@wrap_tool_call
def bounded_tool_result(
    request: ToolCallRequest,
    handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
) -> ToolMessage | Command[Any]:
    result = handler(request)
    if isinstance(result, ToolMessage):
        # ToolNode can return validation errors without raising through error middleware.
        content = json.dumps(result.content, ensure_ascii=False)
        if result.status == "error" or len(content.encode("utf-8")) > RESULT_BYTES:
            return ToolMessage(
                content=TOOL_ERROR,
                name=request.tool_call["name"],
                tool_call_id=request.tool_call["id"],
                status="error",
            )
    return result


class OfflineAgentRunner:
    """Shared bounded framework runner; authenticated callers own admission and tool access."""

    def __init__(
        self,
        model: BaseChatModel,
        tools: Sequence[BaseTool],
        checkpointer: BaseCheckpointSaver,
        *,
        review_tools: frozenset[str] = frozenset(),
        model_limit: int = 4,
        tool_limit: int = 8,
        journal: ExecutionJournal | None = None,
        run_id: UUID | None = None,
        run_timeout: float = 60,
        tool_timeout: float = 10,
        sources: SourceTools | None = None,
        instructions: Callable[[], str] | None = None,
    ) -> None:
        if (
            type(model_limit) is not int
            or type(tool_limit) is not int
            or not 1 <= model_limit <= 4
            or not 1 <= tool_limit <= 8
            or not math.isfinite(run_timeout)
            or not 0 < run_timeout <= 60
            or not math.isfinite(tool_timeout)
            or not 0 < tool_timeout <= 10
        ):
            raise ValueError("Invalid offline execution limits.")
        names = [tool.name for tool in tools]
        if len(names) != len(set(names)) or not review_tools.issubset(names):
            raise ValueError("Invalid offline tool registration.")
        self.run_id = run_id
        self.sources = sources
        self.run_timeout = run_timeout
        self.bounds = BoundedCalls(model_limit, tool_timeout)
        middleware: list[AgentMiddleware[Any, Any]] = [
            ModelCallLimitMiddleware(run_limit=model_limit, exit_behavior="error"),
            ToolCallLimitMiddleware(run_limit=tool_limit, exit_behavior="error"),
            ModelRetryMiddleware(
                max_retries=1,
                retry_on=(ConnectionError,),
                on_failure="error",
                initial_delay=0.05,
                jitter=False,
            ),
            self.bounds,
            ToolErrorMiddleware(on_error=tool_error),
            bounded_tool_result,
            HumanInTheLoopMiddleware(
                interrupt_on={
                    name: {"allowed_decisions": ["approve", "reject"]} for name in review_tools
                }
            ),
        ]
        if journal is not None:
            middleware.insert(4, AccountingMiddleware(journal))
        if sources is not None:
            middleware.append(sources)
        if instructions is not None:
            middleware.append(AssistantInstructions(instructions))
        self.graph = create_agent(
            model=model,
            tools=tools,
            checkpointer=checkpointer,
            middleware=middleware,
        )

    def _config(self, conversation_id: UUID) -> RunnableConfig:
        configurable = {"thread_id": str(conversation_id)}
        if self.run_id is not None:
            configurable["ukladen_run_id"] = str(self.run_id)
        return {"configurable": configurable, "recursion_limit": 32}

    def run(self, request: AgentInput) -> AgentResult:
        if self.sources is not None:
            self.sources.scope = request.source_scope
        with tracing_context(enabled=False):
            config = self._config(request.conversation_id)
            if self.graph.get_state(config).next:
                raise InvalidAgentReview("Conversation has unfinished execution.")
            return self._invoke({"messages": [HumanMessage(content=request.message)]}, config)

    def resume(self, conversation_id: UUID, review: AgentReview) -> AgentResult:
        with tracing_context(enabled=False):
            config = self._config(conversation_id)
            state = self.graph.get_state(config)
            interrupts = [interrupt for task in state.tasks for interrupt in task.interrupts]
            if len(interrupts) != 1 or interrupts[0].id != review.interrupt_id:
                raise InvalidAgentReview("Unknown or stale review.")
            actions = interrupts[0].value["action_requests"]
            if len(actions) != len(review.decisions):
                raise InvalidAgentReview("Every pending action needs a decision.")
            return self._invoke(
                Command(
                    resume={"decisions": [{"type": decision} for decision in review.decisions]}
                ),
                config,
            )

    def _invoke(self, value: InputAgentState | Command[Any], config: RunnableConfig) -> AgentResult:
        self.bounds.begin(self.run_timeout)
        try:
            if stream_sink.get() is None:
                result = self.graph.invoke(value, config)
            else:
                result = {}
                streamed_bytes = 0
                stream: Any = self.graph.stream(value, config, stream_mode=["messages", "values"])
                for mode, data in stream:
                    if mode == "values":
                        result = data
                    elif mode == "messages":
                        message, metadata = data
                        if metadata.get("langgraph_node") != "model":
                            continue
                        # Only visible text crosses transport; never arguments, reasoning or state.
                        content = message.content
                        text = (
                            content
                            if isinstance(content, str)
                            else "".join(
                                block.get("text", "")
                                for block in content
                                if isinstance(block, dict) and block.get("type") == "text"
                            )
                        )
                        streamed_bytes += len(text.encode("utf-8"))
                        if streamed_bytes > RESULT_BYTES * 4:
                            return AgentResult(status="limited")
                        if text:
                            emit("delta", id=message.id or "answer", text=text)
            response = self._result(result)
            return (
                response.model_copy(update={"sources": self.sources.sources})
                if self.sources
                else response
            )
        except CALL_LIMIT_ERRORS:
            return AgentResult(status="limited")
        except TimeoutError:
            return AgentResult(status="failed", error_code="timeout")
        except Exception as error:
            log_failure(logger, "ai.offline_execution_failed", error)
            return AgentResult(status="failed")

    @staticmethod
    def _result(result: Mapping[str, Any]) -> AgentResult:
        if interrupts := result.get("__interrupt__"):
            if len(interrupts) != 1:
                return AgentResult(status="failed")
            interrupt = interrupts[0]
            actions = interrupt.value["action_requests"]
            if len(actions) > 8 or len(json.dumps(actions).encode("utf-8")) > RESULT_BYTES:
                return AgentResult(status="limited")
            return AgentResult(
                status="interrupted",
                review=PendingReview(
                    interrupt_id=interrupt.id,
                    actions=tuple(
                        ReviewAction(tool_name=action["name"], arguments=action["args"])
                        for action in actions
                    ),
                ),
            )
        messages = result["messages"]
        last_user = max(
            i for i, message in enumerate(messages) if isinstance(message, HumanMessage)
        )
        tools = tuple(
            ToolOutcome(
                call_id=message.tool_call_id,
                tool_name=message.name or "",
                status=message.status,
                content=message.text,
            )
            for message in messages[last_user + 1 :]
            if isinstance(message, ToolMessage)
        )
        answer = messages[-1].text if isinstance(messages[-1], AIMessage) else None
        if answer is not None and len(answer.encode("utf-8")) > RESULT_BYTES:
            return AgentResult(status="limited", tools=tools)
        return AgentResult(status="completed", answer=answer, tools=tools)
