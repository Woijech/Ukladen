from dataclasses import replace
from datetime import datetime, timedelta
from typing import Literal

from app.modules.ai.application.persistence import AiRepository
from app.modules.ai.domain.state import ACTIVE_RUN_STATUSES, ErrorCode, Run

RUN_TIMEOUT = timedelta(seconds=60)


def stop_run(
    repository: AiRepository,
    run: Run,
    now: datetime,
    *,
    status: Literal["failed", "cancelled"],
    error: ErrorCode,
) -> Run:
    """Close unknown in-flight outcomes without pretending they did not execute."""
    if run.status not in ACTIVE_RUN_STATUSES:
        return run
    for attempt in repository.attempts(run.user_id, run.id):
        if attempt.status == "started":
            repository.save_attempt(
                replace(attempt, status="interrupted", finished_at=now, error_code=error)
            )
    for tool in repository.tool_executions(run.user_id, run.id):
        if tool.status == "started":
            repository.save_tool_execution(
                replace(tool, status="interrupted", finished_at=now, error_code=error)
            )
    stopped = run.transition(status, now)
    repository.save_run(stopped, run.status)
    return stopped
