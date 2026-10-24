"""Supported OpenRouter transport; the official connector owns protocol conversion."""

import json
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import monotonic
from typing import Any

import httpx
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_openrouter import ChatOpenRouter
from langchain_openrouter.chat_models import _convert_chunk_to_message_chunk, _strip_internal_kwargs
from openrouter import OpenRouter
from openrouter.errors import ResponseValidationError
from pydantic import Field, SecretStr

from app.modules.ai.application.agent import ProviderFailure
from app.modules.ai.application.connections import ModelOffering
from app.modules.ai.domain.connections import ConnectionUnavailable

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


def token_count(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProviderFailure("invalid_response")
    if not 0 <= value <= 2**63 - 1 or int(value) != value:
        raise ProviderFailure("invalid_response")
    return int(value)


def usage_values(data: dict[str, Any]) -> dict[str, int | None]:
    usage = data.get("usage") or {}
    return {
        "input_tokens": token_count(usage.get("prompt_tokens")),
        "output_tokens": token_count(usage.get("completion_tokens")),
    }


def retry_seconds(value: str | None) -> int:
    try:
        seconds = int(value or "60")
    except ValueError:
        try:
            seconds = int((parsedate_to_datetime(value or "") - datetime.now(UTC)).total_seconds())
        except ValueError, TypeError, OverflowError:
            seconds = 60
    return max(1, min(seconds, 86400))


class LimitedStream(httpx.SyncByteStream):
    def __init__(self, stream: httpx.SyncByteStream) -> None:
        self.stream, self.deadline = stream, monotonic() + 60

    def __iter__(self) -> Iterator[bytes]:
        size = 0
        for chunk in self.stream:
            size += len(chunk)
            if size > 131072 or monotonic() >= self.deadline:
                raise ProviderFailure("invalid_response")
            yield chunk

    def close(self) -> None:
        self.stream.close()


class OpenRouterTransport(httpx.BaseTransport):
    def __init__(
        self,
        profile: ModelOffering,
        credential: Callable[[], str],
        backoff: Callable[[int], None],
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.profile, self.credential, self.backoff = profile, credential, backoff
        self.transport = transport or httpx.HTTPTransport(retries=0, trust_env=False)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if str(request.url) != ENDPOINT or request.method != "POST":
            raise ConnectionUnavailable("Unsupported model endpoint.")
        body = json.loads(request.content)
        policy = body.get("provider") or {}
        if (
            policy.get("allow_fallbacks") is not False
            or policy.get("require_parameters") is not True
            or policy.get("data_collection") != "deny"
            or body.get("models")
            or body.get("plugins")
        ):
            raise ConnectionUnavailable("Model routing policy was not preserved.")
        if self.profile.free_only and policy.get("max_price") != {
            "prompt": "0",
            "completion": "0",
            "request": "0",
        }:
            raise ConnectionUnavailable("Free-only routing policy was not preserved.")
        maximum = body.get("max_tokens")
        if (
            type(maximum) is not int
            or not 1 <= maximum <= self.profile.max_output_tokens
            or body.get("max_completion_tokens") is not None
        ):
            raise ConnectionUnavailable("Model output budget was not preserved.")
        if (
            body.get("model") != self.profile.model
            or len(request.content) > self.profile.max_input_bytes
        ):
            raise ConnectionUnavailable("Model request exceeds the configured input budget.")
        if body.get("tools") and not self.profile.tools:
            raise ConnectionUnavailable("Tool calling is unavailable for this model.")
        if body.get("response_format") and (
            not self.profile.structured_output or body.get("tools")
        ):
            raise ConnectionUnavailable("Use a supported separate structured-output request.")
        if body.get("stream") and not self.profile.streaming:
            raise ConnectionUnavailable("Streaming is unavailable for this model.")
        # Resolve again at the dispatch boundary; the model and SDK never retain the real key.
        request.headers["Authorization"] = "Bearer " + self.credential()
        response = self.transport.handle_request(request)
        if response.headers.get("Content-Encoding", "identity") != "identity":
            response.close()
            raise ProviderFailure("invalid_response")
        if response.is_stream_consumed and len(response.content) > 131072:
            response.close()
            raise ProviderFailure("invalid_response")
        if not isinstance(response.stream, httpx.SyncByteStream):
            response.close()
            raise ProviderFailure("invalid_response")
        response.stream = LimitedStream(response.stream)
        if response.status_code in (429, 503):
            self.backoff(retry_seconds(response.headers.get("Retry-After")))
        return response

    def close(self) -> None:
        self.transport.close()


class SupportedOpenRouter(ChatOpenRouter):
    supported_profile: ModelOffering = Field(exclude=True)
    # Async callers must use the same guarded transport rather than the SDK's default client.
    _agenerate = BaseChatModel._agenerate
    _astream = BaseChatModel._astream

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any):
        if tools and not self.supported_profile.tools:
            raise ConnectionUnavailable("Tool calling is unavailable for this model.")
        return super().bind_tools(tools, **kwargs)

    def with_structured_output(self, schema: Any = None, **kwargs: Any):
        if not self.supported_profile.structured_output:
            raise ConnectionUnavailable("Structured output is unavailable for this model.")
        return super().with_structured_output(schema, **kwargs)

    def _create_chat_result(self, response: Any) -> ChatResult:
        data = response if isinstance(response, dict) else response.model_dump(by_alias=True)
        usage = usage_values(data)
        choices = data.get("choices") or []
        if len(choices) != 1 or data.get("model") != self.model_name:
            raise ProviderFailure("invalid_response", **usage)
        choice = choices[0]
        if choice.get("finish_reason") not in ("stop", "tool_calls") or choice.get(
            "message", {}
        ).get("refusal"):
            raise ProviderFailure("invalid_response", **usage)
        result = super()._create_chat_result(response)
        for generation in result.generations:
            message = generation.message
            if not isinstance(message, AIMessage) or message.invalid_tool_calls:
                raise ProviderFailure("invalid_response", **usage)
            message.additional_kwargs = {}
            message.response_metadata = {"ukladen_usage": usage}
            message.usage_metadata = None
        result.llm_output = {"model_name": self.model_name}
        return result

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs):
        try:
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        except ProviderFailure, ConnectionUnavailable:
            raise
        except httpx.TimeoutException:
            raise ProviderFailure("timeout") from None
        except ResponseValidationError as error:
            try:
                reported = usage_values(json.loads(error.body or "{}"))
            except ValueError, TypeError, AttributeError:
                reported = {"input_tokens": None, "output_tokens": None}
            raise ProviderFailure("invalid_response", **reported) from None
        except Exception:
            raise ProviderFailure() from None

    def _stream(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs):
        if not self.supported_profile.streaming:
            raise ConnectionUnavailable("Streaming is unavailable for this model.")
        message_dicts, params = self._create_message_dicts(messages, stop)
        params = params | kwargs | {"stream": True, "stream_options": {"include_usage": True}}
        _strip_internal_kwargs(params)
        usage: dict[str, int | None] = {"input_tokens": None, "output_tokens": None}
        finished = False
        try:
            # Keep raw counts: the connector otherwise replaces missing usage with zero.
            for response in self.client.chat.send(
                messages=message_dicts,
                **params,
            ):
                data = response.model_dump(by_alias=True)
                if data.get("model") != self.model_name:
                    raise ProviderFailure("invalid_response", **usage)
                if data.get("usage"):
                    usage = usage_values(data)
                if data.get("error"):
                    raise ProviderFailure("invalid_response", **usage)
                choices = data.get("choices") or []
                if choices:
                    choice = choices[0]
                    if finished:
                        raise ProviderFailure("invalid_response", **usage)
                    reason = choice.get("finish_reason")
                    if reason is not None:
                        if reason not in ("stop", "tool_calls"):
                            raise ProviderFailure("invalid_response", **usage)
                        finished = True
                    if choice.get("delta", {}).get("refusal"):
                        raise ProviderFailure("invalid_response", **usage)
                    message = _convert_chunk_to_message_chunk(data, AIMessageChunk)
                    if not isinstance(message, AIMessageChunk):
                        raise ProviderFailure("invalid_response", **usage)
                    message.additional_kwargs = {}
                    message.usage_metadata = None
                    message.response_metadata = {}
                    yield ChatGenerationChunk(message=message)
            if not finished:
                raise ProviderFailure("invalid_response", **usage)
            yield ChatGenerationChunk(
                message=AIMessageChunk(content="", response_metadata={"ukladen_usage": usage})
            )
        except ProviderFailure, ConnectionUnavailable:
            raise
        except httpx.TimeoutException:
            raise ProviderFailure("timeout", **usage) from None
        except Exception:
            raise ProviderFailure(
                input_tokens=usage["input_tokens"], output_tokens=usage["output_tokens"]
            ) from None


def openrouter_model(
    profile: ModelOffering,
    credential: Callable[[], str],
    backoff: Callable[[int], None],
    *,
    transport: httpx.BaseTransport | None = None,
) -> tuple[SupportedOpenRouter, httpx.Client]:
    client = httpx.Client(
        transport=OpenRouterTransport(profile, credential, backoff, transport),
        timeout=httpx.Timeout(20, connect=5),
        headers={"Accept-Encoding": "identity"},
        follow_redirects=False,
        trust_env=False,
    )
    sdk = OpenRouter(
        api_key="resolved-at-dispatch",
        server_url="https://openrouter.ai/api/v1",
        client=client,
        retry_config=None,
        timeout_ms=20000,
    )
    provider = {"allow_fallbacks": False, "require_parameters": True, "data_collection": "deny"}
    if profile.free_only:
        provider["max_price"] = {"prompt": "0", "completion": "0", "request": "0"}
    model = SupportedOpenRouter(
        model=profile.model,
        api_key=SecretStr("resolved-at-dispatch"),
        client=sdk,
        supported_profile=profile,
        max_retries=0,
        max_tokens=profile.max_output_tokens,
        openrouter_provider=provider,
        plugins=[],
        session_id=None,
        trace=None,
        cache=False,
    )
    return model, client
