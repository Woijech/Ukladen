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
    assert requests[0]["stage"] == "final_application_request_before_provider_serialization"
    assert requests[0]["tool_schemas"][0]["function"]["name"] == "get_calendar_events"
    assert metrics[0]["fingerprints"]["system"] == metrics[1]["fingerprints"]["system"]
    contents = [data["value"] for kind, data in events if kind == "context_part"]
    assert any(
        item["name"] == "system" and "Answer briefly" in item["content"] for item in contents
    )
    assert any(
        kind == "source_context" and data["value"]["duration_ms"] >= 0 for kind, data in events
    )
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


def test_document_discovery_loads_only_requested_schemas_and_resets_next_turn():
    reader = Mock(spec=SourceReader)
    reader.context.return_value = "Current profile date"
    reader.read.return_value = EvidenceResult(status="not_found")
    sources = SourceTools(reader, uuid4())
    model = FakeChatModel(
        responses=(
            AIMessage(content="", tool_calls=[call("select_tools", {"groups": ["documents"]})]),
            AIMessage(
                content="",
                tool_calls=[call("search_workspace", {"query": "normalization"}, "read")],
            ),
            AIMessage(content="No matching documents"),
        )
    )
    runner = OfflineAgentRunner(
        model, [*sources.build_tools(), action_tool()], InMemorySaver(), sources=sources
    )
    events = []
    token = capture.set(lambda kind, data: events.append((kind, data)))
    request = AgentInput(conversation_id=uuid4(), message="Find my database notes")
    try:
        assert runner.run(request).status == "completed"
        requests = [data["value"] for kind, data in events if kind == "model_request"]
        assert requests[0]["tools"] == ["select_tools"]
        assert set(requests[1]["tools"]) == {
            "select_tools",
            "search_workspace",
            "read_page",
            "read_material_excerpt",
        }
        assert requests[2]["tools"] == requests[1]["tools"]
        reader.read.assert_called()
        events.clear()
        model.responses = (AIMessage(content="Hello"),)
        assert runner.run(request.model_copy(update={"message": "Hello"})).status == "completed"
        requests = [data["value"] for kind, data in events if kind == "model_request"]
        assert requests[0]["tools"] == ["select_tools"]
    finally:
        capture.reset(token)


def test_calendar_action_discovery_preserves_hitl_and_does_not_write():
    reader = Mock(spec=SourceReader)
    reader.context.return_value = "Current profile date"
    sources = SourceTools(reader, uuid4())
    action = {
        "operation": "event_create",
        "title": "Study",
        "starts_at": "2030-11-05T10:00:00+03:00",
        "ends_at": "2030-11-05T11:00:00+03:00",
        "blocks_time": True,
    }
    runner = OfflineAgentRunner(
        FakeChatModel(
            responses=(
                AIMessage(
                    content="",
                    tool_calls=[
                        call(
                            "select_tools",
                            {"groups": ["calendar", "actions"], "operations": ["event_create"]},
                        )
                    ],
                ),
                AIMessage(
                    content="",
                    tool_calls=[call("propose_actions", {"actions": [action]}, "proposal")],
                ),
            )
        ),
        [*sources.build_tools(), action_tool()],
        InMemorySaver(),
        sources=sources,
        review_tools=frozenset({"propose_actions"}),
    )
    events = []
    token = capture.set(lambda kind, data: events.append((kind, data)))
    try:
        result = runner.run(AgentInput(conversation_id=uuid4(), message="Create a study event"))
    finally:
        capture.reset(token)
    assert result.status == "interrupted" and result.review is not None
    assert result.review.actions[0].arguments == {"actions": [action]}
    requests = [data["value"] for kind, data in events if kind == "model_request"]
    assert set(requests[1]["tools"]) == {
        "select_tools",
        "get_calendar_events",
        "get_calendar_availability",
        "propose_actions",
    }
    reader.read.assert_not_called()


def test_action_schema_exposes_only_selected_operations_without_dangling_references():
    from app.modules.ai.infrastructure.action_tools import selected_action_schema

    single = selected_action_schema({"event_create"})
    items = single["function"]["parameters"]["properties"]["actions"]["items"]
    assert items["properties"]["operation"]["const"] == "event_create"
    assert "event_id" not in items["properties"]
    assert "$ref" not in json.dumps(single) and "discriminator" not in json.dumps(single)
    mixed = selected_action_schema({"event_create", "reminder_create"})
    variants = mixed["function"]["parameters"]["properties"]["actions"]["items"]["oneOf"]
    assert {item["properties"]["operation"]["const"] for item in variants} == {
        "event_create",
        "reminder_create",
    }


def test_action_descriptions_only_advertise_the_selected_task_capabilities() -> None:
    from app.modules.ai.infrastructure.action_tools import selected_action_schema

    calendar = selected_action_schema({"event_create"})["function"]["description"]
    page = selected_action_schema({"page_update"})["function"]["description"]
    assert "event_create" in calendar and "page_update" not in calendar
    assert "block_edits" not in calendar and "task extraction" not in calendar.lower()
    assert "block_edits" in page and "event_action" not in page
