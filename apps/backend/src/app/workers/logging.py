import logging
import re
from time import perf_counter
from typing import Any
from uuid import uuid4

from celery import signals

from app.core.config import get_settings
from app.core.logging import (
    configure_logging,
    log_failure,
    request_id,
    task_name,
)
from app.core.logging import (
    task_id as current_task_id,
)

logger = logging.getLogger(__name__)
_TASKS = {"foundation.ping", "auth.send_email", "schedule.sync_group", "schedule.refresh_selected"}


def configure_worker_logging(**kwargs: Any) -> None:
    configure_logging(get_settings().log_level)
    logger.info("worker.logging_ready")


def propagate_request_id(headers: dict[str, Any] | None = None, **kwargs: Any) -> None:
    if headers is not None and request_id.get() is not None:
        headers["ukladen_request_id"] = request_id.get()


def start_task(task: Any = None, task_id: str | None = None, **kwargs: Any) -> None:
    if task is None:
        return
    identifier = (task.request.headers or {}).get("ukladen_request_id")
    if not isinstance(identifier, str) or re.fullmatch(r"[0-9a-f]{32}", identifier) is None:
        identifier = None
    safe_id = task_id if task_id and re.fullmatch(r"[0-9a-f-]{36}", task_id) else uuid4().hex
    task.request.ukladen_log_context = (
        request_id.set(identifier),
        current_task_id.set(safe_id),
        task_name.set(task.name if task.name in _TASKS else "[unknown]"),
        perf_counter(),
    )
    # Redact even malformed payloads before Celery reports failures.
    task.request.update(argsrepr="(<redacted>)", kwargsrepr="{<redacted>}")
    logger.info("task.started")


def finish_task(task: Any = None, state: str | None = None, **kwargs: Any) -> None:
    if task is None:
        return
    context = getattr(task.request, "ukladen_log_context", None)
    if context is None:
        return
    try:
        logger.log(
            logging.ERROR if state == "FAILURE" else logging.INFO,
            "task.finished",
            extra={
                "state": state
                if state in {"SUCCESS", "FAILURE", "RETRY", "REVOKED"}
                else "[unknown]",
                "duration_ms": round((perf_counter() - context[3]) * 1000, 2),
            },
        )
    finally:
        request_id.reset(context[0])
        current_task_id.reset(context[1])
        task_name.reset(context[2])
        del task.request.ukladen_log_context


def fail_task(exception: BaseException | None = None, **kwargs: Any) -> None:
    if exception is not None:
        log_failure(logger, "task.failed", exception)


def install_task_logging() -> None:
    for signal, receiver in (
        (signals.setup_logging, configure_worker_logging),
        (signals.before_task_publish, propagate_request_id),
        (signals.task_prerun, start_task),
        (signals.task_postrun, finish_task),
        (signals.task_failure, fail_task),
    ):
        signal.connect(receiver, weak=False, dispatch_uid=f"ukladen.{receiver.__name__}")
