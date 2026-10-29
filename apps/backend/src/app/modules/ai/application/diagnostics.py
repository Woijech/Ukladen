"""Explicit local diagnostic capture; never exports tracing to an external service."""

import json
import re
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

capture: ContextVar[Callable[[str, object], None] | None] = ContextVar(
    "ai_diagnostics", default=None
)


class DiagnosticReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Literal["unreviewed", "passed", "failed"]
    note: str = Field(default="", max_length=2000)


def bounded_payload(value: object) -> dict:
    """Keep inspectable content, strip credential/reasoning fields, and bound storage."""

    def clean(item: Any, depth: int = 0) -> Any:
        if depth > 12:
            return "[depth limit]"
        if isinstance(item, dict):
            if item.get("type") in ("reasoning", "thinking", "redacted_thinking"):
                return "[reasoning omitted]"
            return {
                str(key): "[redacted]"
                if re.search(
                    r"key|secret|password|authorization|cookie|reasoning|token$", str(key), re.I
                )
                else clean(part, depth + 1)
                for key, part in list(item.items())[:100]
            }
        if isinstance(item, (list, tuple)):
            return [clean(part, depth + 1) for part in item[:100]]
        if isinstance(item, str):
            if item.lstrip().startswith(("{", "[")):
                try:
                    return clean(json.loads(item), depth + 1)
                except ValueError, RecursionError:
                    pass
            return re.sub(r"(?i)\b(?:sk-[\w-]{8,}|bearer\s+[\w.\-/+=]{8,})", "[redacted]", item)
        return item if item is None or isinstance(item, (int, float, bool)) else str(item)

    data = clean(value)
    text = json.dumps(data, ensure_ascii=False, allow_nan=False)
    if len(text.encode()) > 16384:
        return {"truncated": True, "preview": text.encode()[:12000].decode(errors="ignore")}
    return {"value": data}


def record(kind: str, value: object) -> None:
    sink = capture.get()
    if sink is not None:
        sink(kind, bounded_payload(value))
