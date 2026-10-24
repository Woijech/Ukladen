"""Transient presentation events; canonical messages and runs remain in PostgreSQL."""

from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

stream_sink: ContextVar[Callable[[dict[str, Any]], None] | None] = ContextVar(
    "ai_stream_sink", default=None
)


def emit(event: str, **data: Any) -> None:
    if sink := stream_sink.get():
        sink({"event": event, "data": data})
