from copy import deepcopy
from unittest.mock import patch
from uuid import uuid4

import pytest
from deepeval.test_case import ToolCall
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import TypeAdapter

from app.integrations.llm.fake import FakeChatModel
from app.modules.ai.application.agent import AgentInput, AgentReview
from app.modules.ai.infrastructure.action_tools import action_tool
from app.modules.ai.infrastructure.agent import OfflineAgentRunner
from evaluations import scenarios
from evaluations.metrics import ObjectiveMetric, citation_precision, recall_at_k, reciprocal_rank
from evaluations.runtime import observe, score
from evaluations.scenarios import load_suite

DIGEST, SCENARIOS = load_suite()


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.id)
def test_production_agent_synthetic_contract(scenario):
    # Scripted choices assert runtime contracts, not natural-language model quality.
    with patch(
        "socket.socket.connect", side_effect=AssertionError("Offline eval attempted network")
    ):
        cases, record = observe(scenario)
        assert all(turn["passed"] for turn in score(cases))
    if scenario.category == "event_confirmation":
        assert record["statuses"] == ["interrupted"]
    if scenario.id == "error_recovery-networks":
        assert record["recovered_failures"] == 1
    if scenario.category == "injection_isolation" and scenario.source_scope:
        assert record["application_reads_including_revalidation"] == 0


def test_suite_has_twelve_categories_and_explicit_safety_rubrics():
    assert len(DIGEST) == 64 and len(SCENARIOS) == 60
    assert len({case.category for case in SCENARIOS}) == 12
    assert all(
        case.forbidden_actions and case.invariants and case.expected_result for case in SCENARIOS
    )


def test_suite_rejects_invalid_expected_action_batches(tmp_path, monkeypatch):
    cases = deepcopy(SCENARIOS)
    proposal = next(
        call
        for case in cases
        for turn in case.turns
        for call in turn.expected_tools
        if call.name == "propose_actions"
    )
    proposal.arguments = {"actions": [{"type": "execute_sql"}]}
    dataset = tmp_path / "scenarios.json"
    dataset.write_bytes(TypeAdapter(list[scenarios.Scenario]).dump_json(cases))
    monkeypatch.setattr(scenarios, "DATASET", dataset)
    with pytest.raises(ValueError):
        load_suite()


@pytest.mark.parametrize(
    "corruption", ["unsupported", "citation", "missing", "extra", "arguments", "order", "injection"]
)
def test_metrics_reject_corrupted_observations(corruption):
    scenario = next(s for s in SCENARIOS if s.category == "note_search")
    cases, _ = observe(scenario)
    case = deepcopy(cases[0])
    assert score([case])[0]["passed"]
    assert case.actual_output is not None and case.tools_called is not None
    assert case.metadata is not None
    if corruption == "unsupported":
        case.actual_output += "\nAn unsupported synthetic assertion."
    elif corruption == "citation":
        case.actual_output = case.actual_output.replace("[source:", "[source:foreign-")
    elif corruption == "missing":
        case.tools_called = case.tools_called[:1]
    elif corruption == "extra":
        case.tools_called += [ToolCall(name="execute_sql", input_parameters={})]
    elif corruption == "arguments":
        case.tools_called[-1].input_parameters = {"page_id": str(uuid4())}
    elif corruption == "order":
        case.tools_called.reverse()
    else:
        case.metadata["forbidden_content"] = ["PRIVATE_CANARY"]
        case.actual_output += "\nPRIVATE_CANARY"
    assert not score([case])[0]["passed"]


def test_retrieval_and_citation_metrics_penalize_missing_duplicate_and_foreign_results():
    assert recall_at_k(["bad", "b", "b", "a"], {"a", "b"}, 3) == 0.5
    assert reciprocal_rank(["bad", "b", "a"], {"a", "b"}) == 0.5
    assert reciprocal_rank(["bad"], {"a"}) == 0
    assert citation_precision("Fact [source:a] [source:foreign]", {"a"}, {"a"}) == 0.5
    assert citation_precision("No citation", {"a"}, {"a"}) == 0
    for k, relevant in [(0, {"a"}), (1, set())]:
        with pytest.raises(ValueError):
            recall_at_k([], relevant, k)


def test_deepeval_metric_supports_sync_and_async_without_a_judge():
    import asyncio

    case = observe(SCENARIOS[0])[0][0]
    metric = ObjectiveMetric("constant objective", lambda _: 0.25)
    assert metric.measure(case) == asyncio.run(metric.a_measure(case)) == 0.25
    assert not metric.is_successful()


def test_checkpoint_resume_rejects_a_write_and_never_executes_it():
    scenario = next(s for s in SCENARIOS if s.category == "event_confirmation")
    proposal = AIMessage.model_validate(scenario.turns[0].script[0])
    saver = InMemorySaver()
    conversation = uuid4()
    first = OfflineAgentRunner(
        FakeChatModel(responses=(proposal,)),
        [action_tool()],
        saver,
        review_tools=frozenset({"propose_actions"}),
    )
    pending = first.run(AgentInput(conversation_id=conversation, message="Propose the event"))
    assert pending.review is not None and pending.status == "interrupted"
    resumed = OfflineAgentRunner(
        FakeChatModel(responses=(proposal, AIMessage(content="Rejected"))),
        [action_tool()],
        saver,
        review_tools=frozenset({"propose_actions"}),
    )
    with patch(
        "app.modules.ai.infrastructure.action_tools.ActionBatch.model_validate",
        side_effect=AssertionError("Rejected tool must not run"),
    ):
        result = resumed.resume(
            conversation,
            AgentReview(interrupt_id=pending.review.interrupt_id, decisions=("reject",)),
        )
    assert result.status == "completed" and result.answer == "Rejected"
