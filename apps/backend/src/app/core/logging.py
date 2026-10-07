"""Structured diagnostics with explicit context and no exception payloads."""

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
task_id: ContextVar[str | None] = ContextVar("task_id", default=None)
task_name: ContextVar[str | None] = ContextVar("task_name", default=None)

_FIELDS = {
    "event",
    "method",
    "route",
    "status_code",
    "duration_ms",
    "operation",
    "dependency",
    "group_id",
    "group_number",
    "event_count",
    "error_code",
    "reason",
    "user_id",
    "state",
    "queued_count",
    "selected_count",
    "error_type",
    "traceback",
}


def stack_frames(traceback: TracebackType | None) -> list[dict[str, str | int]]:
    """Keep locations, never exception messages, source lines or frame locals."""
    frames: list[dict[str, str | int]] = []
    while traceback is not None:
        code = traceback.tb_frame.f_code
        frames.append(
            {
                "file": Path(code.co_filename).name,
                "line": traceback.tb_lineno,
                "function": code.co_name,
            }
        )
        traceback = traceback.tb_next
    return frames[-30:]


def log_failure(
    logger: logging.Logger,
    event: str,
    error: BaseException,
    *,
    level: int = logging.ERROR,
    **fields: str | int | float | bool | None,
) -> None:
    # Logging the original exception text can expose SQL parameters, tokens or SDK responses.
    logger.log(
        level,
        event,
        extra={
            **fields,
            "event": event,
            "error_type": type(error).__name__,
            "traceback": stack_frames(error.__traceback__),
        },
    )


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        application_record = record.name.startswith("app.")
        data: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            # Third-party messages may contain URLs, credentials or task payloads.
            "event": record.getMessage() if application_record else "runtime.log",
        }
        if application_record:
            data.update(
                {key: value for key in _FIELDS if (value := getattr(record, key, None)) is not None}
            )
        for name, context in (
            ("request_id", request_id),
            ("task_id", task_id),
            ("task_name", task_name),
        ):
            if (value := context.get()) is not None:
                data[name] = value
        if record.exc_info and record.exc_info[1] is not None:
            data["error_type"] = type(record.exc_info[1]).__name__
            data["traceback"] = stack_frames(record.exc_info[2])
        return json.dumps(data, ensure_ascii=True, allow_nan=False)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if not any(handler.get_name() == "ukladen-json" for handler in root.handlers):
        handler = logging.StreamHandler()
        handler.set_name("ukladen-json")
        handler.setFormatter(JsonFormatter())
        root.addHandler(handler)
    root.setLevel(logging.WARNING)
    logging.getLogger("app").setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "celery", "celery.task"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(logging.WARNING)
    # Request diagnostics below replace raw access URLs (including authentication queries).
    logging.getLogger("uvicorn.access").disabled = True
    for name in ("httpx", "httpcore", "boto3", "botocore", "urllib3", "kombu", "amqp"):
        logging.getLogger(name).setLevel(logging.WARNING)
