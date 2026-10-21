"""Scripted offline model; response position is derived from checkpointed messages."""

from collections.abc import Callable, Sequence
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from pydantic import Field


class FakeChatModel(BaseChatModel):
    responses: tuple[AIMessage, ...] = Field(min_length=1)

    @property
    def _llm_type(self) -> str:
        return "ukladen-offline-fake"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        last_user = max(
            i for i, message in enumerate(messages) if isinstance(message, HumanMessage)
        )
        position = sum(isinstance(message, AIMessage) for message in messages[last_user + 1 :])
        if position >= len(self.responses):
            raise ValueError("Offline response script exhausted.")
        # A copy prevents framework-assigned IDs from changing the configured script.
        message = self.responses[position].model_copy(deep=True)
        return ChatResult(generations=[ChatGeneration(message=message)])
