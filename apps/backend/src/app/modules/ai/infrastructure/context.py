"""Keep complete recent turns; tool calls and results must never be split."""

import json

from langchain_core.messages import AnyMessage, HumanMessage


def recent_turns(messages: list[AnyMessage], history_bytes: int = 20000) -> list[AnyMessage]:
    starts = [i for i, message in enumerate(messages) if isinstance(message, HumanMessage)]
    if len(starts) < 2:
        return messages
    keep = starts[-1]
    size = 0
    for index in range(len(starts) - 2, -1, -1):
        segment = messages[starts[index] : starts[index + 1]]
        cost = len(
            json.dumps(
                [message.model_dump() for message in segment], ensure_ascii=False, default=str
            ).encode("utf-8")
        )
        if size + cost > history_bytes:
            break
        size += cost
        keep = starts[index]
    return messages[keep:]
