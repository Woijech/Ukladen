import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel

from app.integrations.llm.openrouter import openrouter_model, retry_seconds
from app.modules.ai.application.agent import AgentInput, ProviderFailure
from app.modules.ai.application.connections import ModelOffering
from app.modules.ai.domain.connections import ConnectionUnavailable
from app.modules.ai.infrastructure.agent import OfflineAgentRunner

PROFILE = ModelOffering(
    id="flash",
    version=1,
    name="Flash",
    model="deepseek/deepseek-v4.1-flash",
    tools=True,
    structured_output=True,
)
KEY = "synthetic-private-openrouter-key"


def completion(content: str = "Synthetic answer", *, usage: Any = None, reason="stop", **message):
    return {
        "id": "synthetic-response",
        "object": "chat.completion",
        "created": 1,
        "model": PROFILE.model,
        "system_fingerprint": None,
        "choices": [
            {
                "index": 0,
                "finish_reason": reason,
                "message": {"role": "assistant", "content": content, **message},
            }
        ],
        **({"usage": usage} if usage is not None else {}),
    }


@pytest.mark.parametrize(
    "usage,expected",
    [
        (None, {"input_tokens": None, "output_tokens": None}),
        (
            {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            {"input_tokens": 0, "output_tokens": 0},
        ),
        (
            {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
            {"input_tokens": 12, "output_tokens": 5},
        ),
    ],
)
def test_official_adapter_uses_exact_model_key_at_dispatch_and_nullable_usage(usage, expected):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=completion(usage=usage), request=request)

    model, client = openrouter_model(
        PROFILE, lambda: KEY, lambda _: None, transport=httpx.MockTransport(respond)
    )
    assert KEY not in repr(model) and KEY not in str(model.to_json())
    with client:
        answer = model.invoke("Synthetic request")
    assert answer.content == "Synthetic answer"
    assert answer.response_metadata["ukladen_usage"] == expected
    assert answer.additional_kwargs == {}
    assert len(requests) == 1 and requests[0].headers["Authorization"] == f"Bearer {KEY}"
    body = json.loads(requests[0].content)
    assert body["model"] == PROFILE.model and body["max_tokens"] == 2048
    assert body["provider"]["allow_fallbacks"] is False
    assert body["provider"]["require_parameters"] is True
    assert "models" not in body and not body.get("plugins")


@pytest.mark.parametrize("status", [401, 402, 403, 429, 500, 503])
def test_errors_do_not_retry_or_switch_keys_and_retry_after_does_not_sleep(status):
    requests, blocked = [], []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            status,
            json={"error": {"message": "secret-provider-error", "code": status}},
            headers={"Retry-After": "13"},
            request=request,
        )

    model, client = openrouter_model(
        PROFILE, lambda: KEY, blocked.append, transport=httpx.MockTransport(respond)
    )
    with client, pytest.raises(ProviderFailure) as failure:
        model.invoke("Synthetic request")
    assert "secret-provider-error" not in str(failure.value)
    assert len(requests) == 1 and blocked == ([13] if status in (429, 503) else [])


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("status", [400, 401, 402, 404, 429, 503])
def test_provider_failures_log_status_and_type_without_private_payload(caplog, stream, status):
    from app.core.logging import JsonFormatter

    sent = []

    def respond(request):
        sent.append(request)
        return httpx.Response(
            status,
            json={"error": {"message": "private-provider-body", "code": status}},
            request=request,
        )

    model, client = openrouter_model(
        PROFILE, lambda: KEY, lambda _: None, transport=httpx.MockTransport(respond)
    )
    with client, pytest.raises(ProviderFailure):
        if stream:
            list(model.stream("private-user-message"))
        else:
            model.invoke("private-user-message")
    records = [record for record in caplog.records if record.msg == "ai.provider_request_failed"]
    assert len(records) == 1 and len(sent) == 1
    row = json.loads(JsonFormatter().format(records[0]))
    assert row["status_code"] == status
    assert row["error_type"] != "ProviderFailure"
    rendered = json.dumps(row)
    assert all(
        secret not in rendered for secret in [KEY, "private-provider-body", "private-user-message"]
    )


@pytest.mark.parametrize(
    "reason,message",
    [
        ("length", {}),
        ("content_filter", {}),
        ("stop", {"refusal": "private-refusal"}),
        (
            "tool_calls",
            {
                "tool_calls": [
                    {
                        "id": "call1",
                        "type": "function",
                        "function": {"name": "double", "arguments": "{"},
                    }
                ]
            },
        ),
    ],
)
def test_refusal_truncation_and_invalid_arguments_fail_with_reported_usage(reason, message):
    payload = completion(
        reason=reason,
        usage={"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        **message,
    )
    model, client = openrouter_model(
        PROFILE,
        lambda: KEY,
        lambda _: None,
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload)),
    )
    with client, pytest.raises(ProviderFailure) as failure:
        model.invoke("Synthetic request")
    assert failure.value.input_tokens == 3 and failure.value.output_tokens == 2


def test_credential_revocation_and_input_bounds_prevent_network_dispatch():
    sent = []

    def revoked():
        raise ConnectionUnavailable()

    def respond(request):
        sent.append(request)
        return httpx.Response(200, json=completion())

    model, client = openrouter_model(
        PROFILE,
        revoked,
        lambda _: None,
        transport=httpx.MockTransport(respond),
    )
    with client:
        with pytest.raises(ConnectionUnavailable):
            model.invoke("Synthetic request")
        with pytest.raises(ConnectionUnavailable):
            model.invoke("я" * 4000)
    assert sent == []


def test_partial_usage_in_an_invalid_provider_response_is_not_fabricated_zero():
    model, client = openrouter_model(
        PROFILE,
        lambda: KEY,
        lambda _: None,
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json=completion(usage={"prompt_tokens": 12}))
        ),
    )
    with client, pytest.raises(ProviderFailure) as failure:
        model.invoke("Synthetic request")
    assert failure.value.input_tokens == 12 and failure.value.output_tokens is None


def test_framework_tool_loop_uses_official_adapter_without_persisting_keys():
    from uuid import uuid4

    @tool
    def double(value: int) -> int:
        """Double a synthetic integer."""
        return value * 2

    answers = iter(
        [
            completion(
                content="",
                reason="tool_calls",
                tool_calls=[
                    {
                        "id": "call1",
                        "type": "function",
                        "function": {"name": "double", "arguments": '{"value":7}'},
                    }
                ],
            ),
            completion("14"),
        ]
    )
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=next(answers))

    model, client = openrouter_model(
        PROFILE, lambda: KEY, lambda _: None, transport=httpx.MockTransport(respond)
    )
    saver = InMemorySaver()
    with client:
        result = OfflineAgentRunner(model, [double], saver).run(
            AgentInput(conversation_id=uuid4(), message="Double seven")
        )
    assert result.status == "completed" and result.answer == "14"
    assert len(requests) == 2 and result.tools[0].status == "success"
    assert KEY not in str(saver.storage) and KEY not in str(saver.writes)


def test_supported_structured_output_and_unsupported_modes_are_explicit():
    class Answer(BaseModel):
        value: int

    model, client = openrouter_model(
        PROFILE,
        lambda: KEY,
        lambda _: None,
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json=completion('{"value":7}'))
        ),
    )
    with client:
        result = model.with_structured_output(Answer, method="json_schema").invoke(
            "Synthetic request"
        )
        assert isinstance(result, Answer) and result.value == 7
    disabled, client = openrouter_model(
        PROFILE.model_copy(update={"tools": False, "structured_output": False}),
        lambda: KEY,
        lambda _: None,
    )
    with client:
        with pytest.raises(ConnectionUnavailable):
            disabled.with_structured_output(Answer)
        with pytest.raises(ConnectionUnavailable):
            disabled.bind_tools([Answer])


class SyntheticStream(httpx.SyncByteStream):
    def __init__(self, events: list[dict]) -> None:
        self.events = events

    def __iter__(self) -> Iterator[bytes]:
        yield b": OPENROUTER PROCESSING\n\n"
        for event in self.events:
            yield ("data: " + json.dumps(event) + "\n\n").encode()
        yield b"data: [DONE]\n\n"


def chunk(delta: dict, finish_reason=None) -> dict:
    return {
        "id": "stream1",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": PROFILE.model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


def test_stream_assembles_arguments_and_preserves_usage_without_reasoning():
    events = [
        chunk({"role": "assistant", "content": "", "reasoning": "private reasoning"}),
        chunk(
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call1",
                        "type": "function",
                        "function": {"name": "double", "arguments": '{"value":'},
                    }
                ]
            }
        ),
        chunk({"tool_calls": [{"index": 0, "function": {"arguments": "7}"}}]}),
        chunk({}, "tool_calls"),
        {
            "id": "stream1",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": PROFILE.model,
            "choices": [],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16},
        },
    ]
    model, client = openrouter_model(
        PROFILE,
        lambda: KEY,
        lambda _: None,
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200, headers={"Content-Type": "text/event-stream"}, stream=SyntheticStream(events)
            )
        ),
    )
    with client:
        chunks = list(model.stream([HumanMessage("Synthetic request")]))
    result = chunks[0]
    for item in chunks[1:]:
        result += item
    assert result.tool_calls[0]["args"] == {"value": 7}
    assert result.response_metadata["ukladen_usage"] == {"input_tokens": 12, "output_tokens": 4}
    assert "private reasoning" not in str(chunks)


def test_reasoning_stream_can_exceed_json_body_bound_without_exposing_reasoning():
    events = [
        chunk({"role": "assistant", "reasoning": "private reasoning fragment " * 20})
        for _ in range(400)
    ]
    events.extend(
        [
            chunk({"content": "Synthetic calendar answer"}),
            chunk({}, "stop"),
            chunk({})
            | {
                "choices": [],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 500,
                    "total_tokens": 512,
                },
            },
        ]
    )
    assert sum(len(json.dumps(event).encode()) for event in events) > 131072
    model, client = openrouter_model(
        PROFILE,
        lambda: KEY,
        lambda _: None,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream; charset=utf-8"},
                stream=SyntheticStream(events),
            )
        ),
    )
    with client:
        chunks = list(model.stream("Synthetic request"))
    assert "".join(chunk.text for chunk in chunks) == "Synthetic calendar answer"
    assert any(
        chunk.response_metadata.get("ukladen_usage", {}).get("output_tokens") == 500
        for chunk in chunks
    )
    assert "private reasoning" not in str(chunks)


def test_stream_body_limit_remains_finite():
    from app.integrations.llm.openrouter import STREAM_BYTES, LimitedStream

    with pytest.raises(ProviderFailure):
        list(LimitedStream(httpx.ByteStream(b"x" * (STREAM_BYTES + 1)), STREAM_BYTES))


@pytest.mark.parametrize("finish", ["stop", "tool_calls"])
@pytest.mark.parametrize("trailing_content", ["", "unexpected answer"])
def test_usage_only_choice_can_repeat_finish_but_cannot_append_content(finish, trailing_content):
    events = [
        chunk({"role": "assistant", "content": "Synthetic answer"}),
        chunk({}, finish),
        chunk({"role": "assistant", "content": trailing_content}, finish)
        | {"usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16}},
    ]
    model, client = openrouter_model(
        PROFILE,
        lambda: KEY,
        lambda _: None,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                stream=SyntheticStream(events),
            )
        ),
    )
    with client:
        if trailing_content:
            with pytest.raises(ProviderFailure):
                list(model.stream("Synthetic request"))
        else:
            chunks = list(model.stream("Synthetic request"))
            assert any(
                chunk.response_metadata.get("ukladen_usage", {}).get("output_tokens") == 4
                for chunk in chunks
            )


def test_framework_stream_runs_calendar_tool_and_completes_answer():
    from uuid import uuid4

    from app.modules.ai.application.source_queries import CalendarRead
    from app.modules.ai.application.streaming import stream_sink
    from app.modules.ai.infrastructure.grounding import SourceTools
    from app.modules.search.application.evidence import EvidenceResult

    reads = []

    class CalendarReader:
        def context(self, user_id):
            return "Current profile date: 2026-10-29; timezone: Europe/Minsk."

        def read(self, user_id, query):
            assert isinstance(query, CalendarRead)
            reads.append(query)
            return EvidenceResult(data={"entries": [{"title": "Synthetic algebra"}]})

    events = iter(
        [
            [
                chunk(
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "calendar-call",
                                "type": "function",
                                "function": {
                                    "name": "get_calendar_events",
                                    "arguments": (
                                        '{"date_from":"2026-10-30","date_to":"2026-10-30"}'
                                    ),
                                },
                            }
                        ],
                    }
                ),
                chunk({}, "tool_calls"),
            ],
            [
                chunk({"role": "assistant", "content": "Завтра синтетическая алгебра."}),
                chunk({}, "stop"),
            ],
        ]
    )
    sent, visible = [], []

    def respond(request):
        sent.append(json.loads(request.content))
        return httpx.Response(
            200, headers={"Content-Type": "text/event-stream"}, stream=SyntheticStream(next(events))
        )

    model, client = openrouter_model(
        PROFILE.model_copy(update={"max_input_bytes": 65536}),
        lambda: KEY,
        lambda _: None,
        transport=httpx.MockTransport(respond),
    )
    source = SourceTools(CalendarReader(), uuid4())
    token = stream_sink.set(visible.append)
    try:
        with client:
            result = OfflineAgentRunner(
                model,
                source.build_tools(),
                InMemorySaver(),
                sources=source,
            ).run(AgentInput(conversation_id=uuid4(), message="Какие завтра пары?"))
    finally:
        stream_sink.reset(token)
    assert result.status == "completed" and result.answer == "Завтра синтетическая алгебра."
    assert reads and len(sent) == 2
    assert all(request["stream"] for request in sent)
    assert any(event["event"] == "delta" for event in visible)


def test_incomplete_stream_never_finishes_a_tool_call():
    events = [chunk({"content": "partial"})]
    model, client = openrouter_model(
        PROFILE,
        lambda: KEY,
        lambda _: None,
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200, headers={"Content-Type": "text/event-stream"}, stream=SyntheticStream(events)
            )
        ),
    )
    with client, pytest.raises(ProviderFailure):
        list(model.stream("Synthetic request"))
    assert retry_seconds("99999999") == 86400
    assert retry_seconds("invalid") == 60


@pytest.mark.parametrize("reason", ["length", "content_filter"])
def test_failed_stream_keeps_trailing_usage_and_never_finishes_tool_call(reason, caplog):
    events = [
        chunk({"content": "partial"}),
        chunk({}, reason),
        chunk({})
        | {
            "choices": [],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16},
        },
    ]
    model, client = openrouter_model(
        PROFILE,
        lambda: KEY,
        lambda _: None,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, headers={"Content-Type": "text/event-stream"}, stream=SyntheticStream(events)
            )
        ),
    )
    with client, pytest.raises(ProviderFailure) as failure:
        list(model.stream("Synthetic request"))
    assert failure.value.input_tokens == 12 and failure.value.output_tokens == 4
    record = next(record for record in caplog.records if record.msg == "ai.provider_request_failed")
    assert record.reason == ("stream_output_limit" if reason == "length" else "stream_refusal")


@pytest.mark.parametrize("failure", ["model", "oversized", "compression", "timeout"])
def test_mismatched_models_and_transport_bounds_fail_safely(failure):
    def respond(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("private transport details")
        payload = completion("x" * 131073 if failure == "oversized" else "Synthetic")
        if failure == "model":
            payload["model"] = "another/model"
        response = httpx.Response(200, json=payload)
        if failure == "compression":
            response.headers["Content-Encoding"] = "gzip"
        return response

    model, client = openrouter_model(
        PROFILE, lambda: KEY, lambda _: None, transport=httpx.MockTransport(respond)
    )
    with client, pytest.raises(ProviderFailure) as error:
        model.invoke("Synthetic")
    assert "private" not in str(error.value)
    if failure == "timeout":
        assert error.value.error_code == "timeout"


def test_free_profile_forbids_nonzero_prices_and_combined_modes():
    sent = []

    def respond(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=completion())

    model, client = openrouter_model(
        PROFILE.model_copy(update={"free_only": True}),
        lambda: KEY,
        lambda _: None,
        transport=httpx.MockTransport(respond),
    )
    with client:
        model.invoke("Synthetic")
        with pytest.raises(ConnectionUnavailable):
            model.invoke(
                "Synthetic",
                response_format={"type": "json_object"},
                tools=[
                    {
                        "type": "function",
                        "function": {"name": "double", "parameters": {"type": "object"}},
                    }
                ],
            )
    assert len(sent) == 1 and sent[0]["provider"]["max_price"] == {
        "prompt": "0",
        "completion": "0",
        "request": "0",
    }


def test_missing_routing_policy_or_overridden_output_budget_never_reaches_provider():
    sent = []

    def respond(request):
        sent.append(request)
        return httpx.Response(200, json=completion())

    model, client = openrouter_model(
        PROFILE, lambda: KEY, lambda _: None, transport=httpx.MockTransport(respond)
    )
    with client:
        with pytest.raises(ConnectionUnavailable):
            model.invoke("Synthetic", max_tokens=100000)
        model.openrouter_provider = {}
        with pytest.raises(ConnectionUnavailable):
            model.invoke("Synthetic")
    assert sent == []
