"""Exercise the production create_agent runner with synthetic application-port evidence."""

import json
from time import perf_counter
from typing import Any
from uuid import UUID, uuid5

from deepeval.test_case import LLMTestCase, ToolCall
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import Field

from app.integrations.llm.fake import FakeChatModel
from app.modules.ai.application.agent import AgentInput
from app.modules.ai.application.source_queries import READ_QUERIES, PlanStatusRead, ReadQuery
from app.modules.ai.infrastructure.action_tools import action_tool
from app.modules.ai.infrastructure.agent import OfflineAgentRunner
from app.modules.ai.infrastructure.grounding import SourceTools
from app.modules.search.application.evidence import EvidenceResult
from evaluations.metrics import ObjectiveMetric, fixture_scores
from evaluations.scenarios import Scenario

OWNER = UUID("11111111-1111-4111-8111-111111111111")


class RecordingModel(FakeChatModel):
    seen: list[list[BaseMessage]] = Field(default_factory=list)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(messages)
        return super()._generate(messages, stop, run_manager, **kwargs)


class SyntheticReader:
    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario
        self.reads: list[ReadQuery] = []
        self.failed: set[int] = set()

    def context(self, user_id: UUID) -> str:
        assert user_id == OWNER
        return "Current profile time: 2030-11-04T09:00:00+03:00; timezone: Europe/Minsk."

    def read(self, user_id: UUID, query: ReadQuery) -> EvidenceResult:
        assert user_id == OWNER
        self.reads.append(query)
        for index, fixture in enumerate(self.scenario.fixtures):
            expected = READ_QUERIES[fixture.tool].model_validate(fixture.arguments)
            matches = query == expected
            if isinstance(query, PlanStatusRead):
                data = fixture.result.data
                matches = isinstance(data, dict) and data.get("plan_id") == str(query.plan_id)
            if matches:
                if fixture.fail_once and index not in self.failed:
                    self.failed.add(index)
                    raise RuntimeError("Synthetic private failure details; must be sanitized")
                return fixture.result
        return EvidenceResult(status="not_found")


def observe(scenario: Scenario, model=None) -> tuple[list[LLMTestCase], dict[str, Any]]:
    reader = SyntheticReader(scenario)
    sources = SourceTools(reader, OWNER)
    scripted = model is None
    model = model or RecordingModel(responses=(AIMessage(content="Unused"),))
    saver = InMemorySaver()
    runner = OfflineAgentRunner(
        model,
        [*sources.build_tools(), action_tool()],
        saver,
        sources=sources,
        review_tools=frozenset({"propose_actions"}),
    )
    conversation = uuid5(OWNER, scenario.id)
    cases, statuses = [], []
    messages: list[BaseMessage] = []
    started = perf_counter()
    for index, turn in enumerate(scenario.turns):
        if scripted:
            model.responses = tuple(AIMessage.model_validate(message) for message in turn.script)
        result = runner.run(
            AgentInput(
                conversation_id=conversation,
                message=turn.request,
                source_scope=scenario.source_scope,
                source_only=scenario.source_only,
            )
        )
        state = runner.graph.get_state(runner._config(conversation)).values
        messages = state.get("messages", [])
        last_user = max(
            i for i, message in enumerate(messages) if isinstance(message, HumanMessage)
        )
        calls = [
            ToolCall(name=call["name"], input_parameters=call["args"])
            for message in messages[last_user + 1 :]
            if isinstance(message, AIMessage)
            for call in message.tool_calls
        ]
        evidence = []
        for message in model.seen[-1] if scripted else messages[last_user + 1 :]:
            if isinstance(message, ToolMessage):
                try:
                    observed = EvidenceResult.model_validate_json(message.text)
                except ValueError:
                    continue
                if observed.sources:
                    evidence.append(observed.model_dump_json())
        cases.append(
            LLMTestCase(
                name=f"{scenario.id}/{index + 1}",
                input=turn.request,
                actual_output=result.answer or "",
                tools_called=calls,
                expected_tools=[
                    ToolCall(name=c.name, input_parameters=c.arguments) for c in turn.expected_tools
                ],
                retrieval_context=evidence,
                metadata={
                    "allowed_tools": scenario.allowed_tools,
                    "required_facts": turn.required_facts,
                    "supported_claims": turn.supported_claims,
                    "forbidden_content": scenario.forbidden_content,
                    "required_citations": turn.required_citations,
                    "available_sources": [source.id for source in result.sources],
                    "relevant_context": [
                        f.result.model_dump_json() for f in scenario.fixtures if f.result.sources
                    ],
                    "status": result.status,
                    "expected_status": turn.expected_status,
                    "review_present": result.review is not None,
                },
            )
        )
        statuses.append(result.status)
    return cases, {
        "id": scenario.id,
        "category": scenario.category,
        "statuses": statuses,
        "elapsed_ms": round((perf_counter() - started) * 1000, 3),
        "model_calls": len(model.seen) if scripted else None,
        "model_input_bytes": sum(
            len(json.dumps([m.model_dump(mode="json") for m in batch]).encode())
            for batch in model.seen
        )
        if scripted
        else None,
        "tool_calls": sum(len(case.tools_called or []) for case in cases),
        "application_reads_including_revalidation": len(reader.reads),
        "recovered_failures": len(reader.failed),
        "reported_usage": [
            message.response_metadata["ukladen_usage"]
            for message in messages
            if isinstance(message, AIMessage) and "ukladen_usage" in message.response_metadata
        ],
    }


def score(cases: list[LLMTestCase]) -> list[dict[str, Any]]:
    results = []
    for case in cases:
        scores = fixture_scores(case)
        metrics = [
            ObjectiveMetric(name, lambda c, key=name: fixture_scores(c)[key]) for name in scores
        ]
        values = {metric.__name__: metric.measure(case) for metric in metrics}
        results.append(
            {
                "name": case.name,
                "passed": all(value >= 1.0 for value in values.values()),
                "metrics": values,
            }
        )
    return results
