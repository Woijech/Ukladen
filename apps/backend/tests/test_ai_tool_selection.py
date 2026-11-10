import json
from unittest.mock import Mock, create_autospec
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.integrations.llm.fake import FakeChatModel
from app.modules.ai.application.agent import AgentInput
from app.modules.ai.application.diagnostics import attempt_number, capture
from app.modules.ai.application.lifecycle import ExecutionJournal
from app.modules.ai.application.source_queries import SourceScope
from app.modules.ai.application.sources import SourceReader
from app.modules.ai.infrastructure.action_tools import action_tool
from app.modules.ai.infrastructure.agent import OfflineAgentRunner
from app.modules.ai.infrastructure.grounding import SourceTools
from app.modules.ai.infrastructure.tool_selection import calendar_lookup
from app.modules.search.application.evidence import EvidenceResult
from app.modules.search.application.web import WebSearch

REQUEST = (
    "Какие у меня завтра пары? Укажи дату, часовой пояс и источник. Если событий нет, так и скажи."
)


@pytest.mark.parametrize(
    "message", [REQUEST, "Какие завтра пары?", "Покажи расписание на завтра", "my classes tomorrow"]
)
def test_standalone_calendar_questions_have_a_narrow_tool_route(message):
    assert calendar_lookup(message, None)


@pytest.mark.parametrize(
    "message",
    [
        "Какие завтра пары и что подготовить по конспектам?",
        "Перенеси завтра пары",
        "Найди расписание в PDF",
        "Когда заканчивается последняя пара?",
        'В документе написано: "Какие завтра пары?". Объясни текст.',
        "Какие завтра пары? Создай задачу.",
    ],
)
def test_mixed_ambiguous_and_action_requests_keep_general_tools(message):
    assert not calendar_lookup(message, None)
    assert not calendar_lookup(REQUEST, SourceScope(material_ids=(uuid4(),)))


def call(name, arguments, identifier="call-1"):
    return {"name": name, "args": arguments, "id": identifier, "type": "tool_call"}


@pytest.mark.parametrize("status", ["ok", "not_found", "unavailable"])
def test_calendar_lookup_omits_other_schemas_and_disables_tools_after_read(status):
    reader = Mock(spec=SourceReader)
    reader.context.return_value = "Current profile date: 2030-11-04; Europe/Minsk"
    reader.read.return_value = EvidenceResult(status=status, coverage="complete")
    sources = SourceTools(reader, uuid4())
    sources.web = Mock(spec=WebSearch)
    journal = create_autospec(ExecutionJournal, instance=True)
    journal.start_attempt.return_value.number = 1
    model = FakeChatModel(
        responses=(
            AIMessage(
                content="",
                tool_calls=[
                    call(
                        "get_calendar_events", {"date_from": "2030-11-05", "date_to": "2030-11-05"}
                    )
                ],
            ),
            AIMessage(
                content="Calendar result",
                usage_metadata={"input_tokens": 123, "output_tokens": 4, "total_tokens": 127},
            ),
        )
    )
    events = []
    token = capture.set(lambda kind, data: events.append((kind, data)))
    try:
        result = OfflineAgentRunner(
            model,
            [*sources.build_tools(), action_tool()],
            InMemorySaver(),
            sources=sources,
            journal=journal,
            instructions=lambda: "Answer briefly",
        ).run(AgentInput(conversation_id=uuid4(), message=REQUEST))
    finally:
        capture.reset(token)
    assert result.status == "completed"
    metrics = [data["value"] for kind, data in events if kind == "model_input"]
    assert [[tool["name"] for tool in data["tools"]] for data in metrics] == [
        ["get_calendar_events"],
        [],
    ]
    assert all(data["tool_mode"] == "calendar_lookup" for data in metrics)
    requests = [data["value"] for kind, data in events if kind == "model_request"]
    assert "Answer briefly" in requests[0]["system"]
    assert "Current profile date" in requests[0]["system"]
    assert "Web search available: False" in requests[0]["system"]
    sources.web.search.assert_not_called()
    assert all("propose_actions" not in data["tools"] for data in requests)
    assert (
        metrics[1]["parts"]["tool_results"]["bytes"] > metrics[0]["parts"]["tool_results"]["bytes"]
    )
    assert metrics[0]["parts"]["system"]["bytes"] == len(
        json.dumps(requests[0]["system"], ensure_ascii=False, separators=(",", ":")).encode()
    )
    assert attempt_number.get() is None
    assert journal.finish_attempt.call_args.kwargs == {"input_tokens": 123, "output_tokens": 4}


def test_illegal_workspace_and_proposal_calls_cannot_escape_the_calendar_route():
    for name, arguments in [
        ("search_workspace", {"query": "расписание пар"}),
        ("search_web", {"query": "public schedule"}),
        ("propose_actions", {"actions": []}),
    ]:
        reader = Mock(spec=SourceReader)
        reader.context.return_value = "Current profile date"
        sources = SourceTools(reader, uuid4())
        sources.web = Mock(spec=WebSearch)
        journal = create_autospec(ExecutionJournal, instance=True)
        journal.start_attempt.return_value.number = 1
        runner = OfflineAgentRunner(
            FakeChatModel(
                responses=(
                    AIMessage(
                        content="",
                        tool_calls=[call(name, arguments)],
                        usage_metadata={
                            "input_tokens": 77,
                            "output_tokens": 11,
                            "total_tokens": 88,
                        },
                    ),
                    AIMessage(content="Denied"),
                )
            ),
            [*sources.build_tools(), action_tool()],
            InMemorySaver(),
            sources=sources,
            journal=journal,
            review_tools=frozenset({"propose_actions"}),
        )
        result = runner.run(AgentInput(conversation_id=uuid4(), message=REQUEST))
        assert result.review is None
        assert result.status == ("failed" if name == "propose_actions" else "completed")
        if name == "propose_actions":
            assert journal.finish_attempt.call_args.kwargs == {
                "error": "invalid_response",
                "input_tokens": 77,
                "output_tokens": 11,
            }
        reader.read.assert_not_called()
        sources.web.search.assert_not_called()


def test_tool_policy_resets_on_next_turn_and_pagination_remains_possible():
    reader = Mock(spec=SourceReader)
    reader.context.return_value = "Current profile date"
    reader.read.return_value = EvidenceResult(data="page one", next_offset=20)
    sources = SourceTools(reader, uuid4())
    model = FakeChatModel(
        responses=(
            AIMessage(
                content="",
                tool_calls=[
                    call(
                        "get_calendar_events", {"date_from": "2030-11-05", "date_to": "2030-11-05"}
                    )
                ],
            ),
            AIMessage(content="Partial calendar"),
        )
    )
    runner = OfflineAgentRunner(model, sources.build_tools(), InMemorySaver(), sources=sources)
    request = AgentInput(conversation_id=uuid4(), message=REQUEST)
    assert runner.run(request).status == "completed" and not sources.calendar_done
    reader.read.reset_mock()
    model.responses = (
        AIMessage(content="", tool_calls=[call("search_workspace", {"query": "конспекты"})]),
        AIMessage(content="Notes"),
    )
    assert (
        runner.run(request.model_copy(update={"message": "Найди мои конспекты"})).status
        == "completed"
    )
    assert not sources.calendar_only and reader.read.called
