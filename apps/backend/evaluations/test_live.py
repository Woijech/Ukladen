import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from evaluations.live import LiveBudget, LiveConfig, execute

EXAMPLE = Path(__file__).with_name("live.example.json")


def configuration(**changes):
    return LiveConfig.model_validate(json.loads(EXAMPLE.read_text()) | changes)


def test_live_request_and_cost_reservations_cannot_be_exceeded():
    config = configuration(max_requests=2)
    budget = LiveBudget(config)
    budget.admit()
    budget.admit()
    with pytest.raises(RuntimeError, match="budget exhausted"):
        budget.admit()
    assert budget.requests == 2 and budget.reserved <= config.max_cost_usd
    cost = LiveBudget(configuration(max_cost_usd=Decimal("0.000001")))
    with pytest.raises(RuntimeError):
        cost.admit()
    assert cost.requests == 0 and cost.reserved == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"max_requests": True},
        {"max_requests": 0},
        {"max_input_bytes": 100000},
        {"max_output_tokens": 100000},
        {"max_cost_usd": "NaN"},
        {"input_usd_per_million": "-1"},
        {"provider": "guessed"},
        {"model": "openrouter/auto"},
        {"model": "openrouter/free"},
        {"model": "vendor/model:online"},
        {"case_ids": ["a", "a"]},
    ],
)
def test_live_configuration_rejects_unbounded_or_implicit_choices(changes):
    with pytest.raises(ValidationError):
        configuration(**changes)


def test_live_harness_uses_mock_transport_only_and_reserves_each_tool_loop_call(monkeypatch):
    config = configuration(max_requests=2)
    monkeypatch.setenv("UKLADEN_EVAL_API_KEY", "synthetic-evaluation-key")
    sent = []

    def respond(request):
        body = json.loads(request.content)
        sent.append(body)
        assert request.headers["Authorization"] == "Bearer synthetic-evaluation-key"
        return httpx.Response(
            200,
            json={
                "id": "synthetic",
                "object": "chat.completion",
                "created": 1,
                "system_fingerprint": None,
                "model": config.model,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "read-" + str(len(sent)),
                                    "type": "function",
                                    "function": {
                                        "name": "search_workspace",
                                        "arguments": '{"query":"networks","source":"page"}',
                                    },
                                }
                            ],
                        },
                    }
                ],
            },
        )

    report = execute(config, transport=httpx.MockTransport(respond))
    assert len(sent) == report["provider_requests_reserved"] == 2
    assert report["cases"][0]["statuses"] == ["failed"]
    assert all(body["model"] == config.model for body in sent)
    assert all(body["max_tokens"] == config.max_output_tokens for body in sent)
    assert all(
        body["provider"]["max_price"]
        == {
            "prompt": str(config.input_usd_per_million),
            "completion": str(config.output_usd_per_million),
            "request": "0",
        }
        for body in sent
    )
    assert "synthetic-evaluation-key" not in json.dumps(report)
    assert report["model_quality_gate"] == "requires_semantic_and_safety_review"


def test_cost_exhaustion_and_unknown_cases_do_not_dispatch_or_read_keys():
    def forbidden(request):
        raise AssertionError("No dispatch allowed")

    report = execute(
        configuration(max_cost_usd=Decimal("0.000001")), transport=httpx.MockTransport(forbidden)
    )
    assert not report["all_selected_cases_executed"] and report["provider_requests_reserved"] == 0
    with pytest.raises(ValueError, match="Unknown"):
        execute(configuration(case_ids=["unknown"]), transport=httpx.MockTransport(forbidden))


@pytest.mark.parametrize("status", [429, 503])
def test_provider_backoff_stops_the_live_suite_without_retry(monkeypatch, status):
    monkeypatch.setenv("UKLADEN_EVAL_API_KEY", "synthetic-evaluation-key")
    sent = []

    def respond(request):
        sent.append(request)
        return httpx.Response(
            status,
            json={"error": {"message": "Synthetic", "code": status}},
            headers={"Retry-After": "13"},
        )

    report = execute(
        configuration(case_ids=["note_search-networks", "note_search-physics"]),
        transport=httpx.MockTransport(respond),
    )
    assert len(sent) == report["provider_requests_reserved"] == 1
    assert report["provider_retry_after_seconds"] == 13
    assert not report["all_selected_cases_executed"]
