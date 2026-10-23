from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from threading import BoundedSemaphore, Lock
from time import monotonic
from typing import Any

from langchain.agents.middleware import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
)
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain_core.messages import ToolMessage
from langgraph.types import Command

# shortcut: threads cannot stop synchronous handlers; require transport deadlines before real tools.
_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="ai-call")
_slots = BoundedSemaphore(8)


class BoundedCalls(AgentMiddleware):
    """Bounds synchronous dispatch without adding another model/tool loop."""

    def __init__(self, model_limit: int, tool_timeout: float) -> None:
        self.model_limit, self.tool_timeout = model_limit, tool_timeout
        self.lock = Lock()
        self.deadline = 0.0
        self.model_calls = 0

    def begin(self, seconds: float) -> None:
        self.deadline = monotonic() + seconds
        self.model_calls = 0

    def call[T](self, handler: Callable[[], T], *, model: bool = False) -> T:
        remaining = self.deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError("AI execution deadline exceeded.")
        slots = _slots
        if not slots.acquire(blocking=False):
            raise RuntimeError("AI execution capacity is unavailable.")

        def dispatch() -> T:
            if monotonic() >= self.deadline:
                raise TimeoutError("AI execution deadline exceeded.")
            if model:
                with self.lock:
                    if self.model_calls >= self.model_limit:
                        raise ModelCallLimitExceededError(
                            0, self.model_calls, None, self.model_limit
                        )
                    self.model_calls += 1
            return handler()

        try:
            future = _executor.submit(copy_context().run, dispatch)
        except BaseException:
            slots.release()
            raise
        future.add_done_callback(lambda _: slots.release())
        timeout = remaining if model else min(remaining, self.tool_timeout)
        result = future.result(timeout=timeout)
        if monotonic() >= self.deadline:
            raise TimeoutError("AI execution deadline exceeded.")
        return result

    def wrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]
    ) -> ModelResponse:
        return self.call(lambda: handler(request), model=True)

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        return self.call(lambda: handler(request))
