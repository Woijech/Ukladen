from threading import Event
from typing import Any
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from langgraph.checkpoint.memory import InMemorySaver

from app.integrations.llm.fake import FakeChatModel
from app.modules.ai.application.agent import AgentInput
from app.modules.ai.application.streaming import stream_sink
from app.modules.ai.domain.preferences import AssistantPreferences
from app.modules.ai.domain.state import InvalidAiState
from app.modules.ai.infrastructure.agent import OfflineAgentRunner


class StreamingModel(FakeChatModel):
    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        contents: list[Any] = ["Hello ", [{"type": "reasoning", "text": "PRIVATE"}], "world"]
        for content in contents:
            yield ChatGenerationChunk(message=AIMessageChunk(content=content))


def test_stream_emits_only_visible_text_and_commits_the_framework_result() -> None:
    events = []
    token = stream_sink.set(events.append)
    try:
        runner = OfflineAgentRunner(
            StreamingModel(responses=(AIMessage(content="unused"),)),
            [],
            InMemorySaver(),
            instructions=lambda: "Be brief.",
        )
        result = runner.run(AgentInput(conversation_id=uuid4(), message="Hello"))
    finally:
        stream_sink.reset(token)
    assert result.status == "completed"
    assert (
        "".join(event["data"]["text"] for event in events if event["event"] == "delta")
        == "Hello world"
    )
    assert "PRIVATE" not in str(events)


@pytest.mark.parametrize("text", ["я" * 4097, "\ud800", "x\x00y"])
def test_instruction_boundary(text: str) -> None:
    with pytest.raises(InvalidAiState):
        AssistantPreferences(text)


def test_visible_token_is_delivered_before_model_completion() -> None:
    received = Event()

    class LiveModel(FakeChatModel):
        def _stream(self, messages, stop=None, run_manager=None, **kwargs):
            yield ChatGenerationChunk(message=AIMessageChunk(content="First"))
            assert received.wait(3), "The first token was buffered until completion."
            yield ChatGenerationChunk(message=AIMessageChunk(content=" second"))

    def sink(event):
        if event["event"] == "delta" and event["data"]["text"] == "First":
            received.set()

    token = stream_sink.set(sink)
    try:
        agent = OfflineAgentRunner(
            LiveModel(responses=(AIMessage(content="unused"),)), [], InMemorySaver()
        )
        result = agent.run(AgentInput(conversation_id=uuid4(), message="Hello"))
    finally:
        stream_sink.reset(token)
    assert received.is_set() and result.status == "completed" and result.answer == "First second"
