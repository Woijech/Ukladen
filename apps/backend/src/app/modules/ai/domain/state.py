import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Literal
from uuid import UUID

from app.modules.ai.domain.pricing import PriceSnapshot
from app.modules.search.domain.evidence import SourceReference

RunStatus = Literal["queued", "running", "completed", "failed", "cancelled", "interrupted"]
ExecutionStatus = Literal["started", "succeeded", "failed", "interrupted", "rejected"]
MessageRole = Literal["user", "assistant", "tool"]
ErrorCode = Literal["unavailable", "invalid_response", "timeout", "cancelled", "interrupted"]
ACTIVE_RUN_STATUSES = ("queued", "running", "interrupted")
TERMINAL_RUN_STATUSES = ("completed", "failed", "cancelled")


class AiNotFound(Exception):
    pass


class AiConflict(Exception):
    pass


class AiPersistenceUnavailable(Exception):
    pass


class InvalidAiState(ValueError):
    pass


def require_time(*values: datetime | None) -> None:
    if any(value is not None and value.utcoffset() is None for value in values):
        raise InvalidAiState("AI timestamps must be timezone-aware.")


def require_label(value: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", value):
        raise InvalidAiState("Invalid AI metadata label.")


@dataclass(frozen=True, kw_only=True)
class Conversation:
    id: UUID
    user_id: UUID
    title: str = field(repr=False)
    created_at: datetime
    last_user_message_at: datetime | None = None
    next_sequence: int = 1
    offering_id: str | None = None
    offering_version: int | None = None
    connection_id: UUID | None = None
    provider: str = "fake"
    model: str = "fake-v1"

    def __post_init__(self) -> None:
        require_time(self.created_at, self.last_user_message_at)
        require_selection(self.offering_id, self.offering_version, self.connection_id)
        require_label(self.provider)
        require_label(self.model)
        if not 1 <= len(self.title.strip()) <= 200 or self.title != self.title.strip():
            raise InvalidAiState("Invalid conversation title.")
        if self.next_sequence < 1 or (
            self.last_user_message_at is not None and self.last_user_message_at < self.created_at
        ):
            raise InvalidAiState("Invalid conversation state.")


@dataclass(frozen=True, kw_only=True)
class Message:
    id: UUID
    user_id: UUID
    conversation_id: UUID
    sequence: int
    role: MessageRole
    content: str = field(repr=False)
    created_at: datetime
    sources: tuple[SourceReference, ...] = ()

    def __post_init__(self) -> None:
        require_time(self.created_at)
        try:
            size = len(self.content.encode("utf-8"))
        except UnicodeEncodeError:
            raise InvalidAiState("Invalid message encoding.") from None
        if self.role not in ("user", "assistant", "tool") or not 1 <= size <= 16384:
            raise InvalidAiState("Invalid stored message.")
        if self.sequence < 1:
            raise InvalidAiState("Invalid message sequence.")
        if len(self.sources) > 64 or (self.sources and self.role != "assistant"):
            raise InvalidAiState("Invalid message source references.")


@dataclass(frozen=True, kw_only=True)
class Run:
    id: UUID
    user_id: UUID
    conversation_id: UUID | None
    submission_id: UUID
    request_digest: str = field(repr=False)
    provider: str
    model: str
    status: RunStatus
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None = None
    version: int = 1
    offering_id: str | None = None
    offering_version: int | None = None
    connection_id: UUID | None = None
    price: PriceSnapshot | None = None

    def __post_init__(self) -> None:
        require_time(self.created_at, self.updated_at, self.finished_at)
        require_selection(self.offering_id, self.offering_version, self.connection_id)
        require_label(self.provider)
        require_label(self.model)
        if not re.fullmatch(r"[0-9a-f]{64}", self.request_digest):
            raise InvalidAiState("Invalid submission digest.")
        if self.version < 1 or self.status not in (*ACTIVE_RUN_STATUSES, *TERMINAL_RUN_STATUSES):
            raise InvalidAiState("Invalid run status.")
        if (
            self.updated_at < self.created_at
            or ((self.status in TERMINAL_RUN_STATUSES) != (self.finished_at is not None))
            or (self.finished_at is not None and self.finished_at != self.updated_at)
        ):
            raise InvalidAiState("Invalid run timestamps.")

    def transition(self, status: RunStatus, now: datetime) -> Run:
        require_time(now)
        if status == self.status:
            return self
        require_run_transition(self.status, status)
        if now < self.updated_at:
            raise AiConflict("Run transition is unavailable.")
        return replace(
            self,
            status=status,
            updated_at=now,
            finished_at=now if status in TERMINAL_RUN_STATUSES else None,
            version=self.version + 1,
        )


def require_run_transition(source: RunStatus, target: RunStatus) -> None:
    allowed = {
        "queued": {"running", "failed", "cancelled"},
        "running": {"completed", "failed", "cancelled", "interrupted"},
        "interrupted": {"running", "failed", "cancelled"},
    }
    if target not in allowed.get(source, set()):
        raise AiConflict("Run transition is unavailable.")


def require_selection(
    offering_id: str | None, version: int | None, connection_id: UUID | None
) -> None:
    if offering_id is None:
        if version is not None or connection_id is not None:
            raise InvalidAiState("A model offering is required.")
    elif (
        not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", offering_id)
        or type(version) is not int
        or not 1 <= version <= 2**31 - 1
    ):
        raise InvalidAiState("Invalid model selection.")


@dataclass(frozen=True, kw_only=True)
class ProviderAttempt:
    id: UUID
    user_id: UUID
    run_id: UUID
    number: int
    status: ExecutionStatus
    started_at: datetime
    finished_at: datetime | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    error_code: ErrorCode | None = None

    def __post_init__(self) -> None:
        require_execution(self.status, self.started_at, self.finished_at, self.error_code)
        if not 1 <= self.number <= 4 or self.status == "rejected":
            raise InvalidAiState("Invalid provider attempt.")
        for tokens in (self.input_tokens, self.output_tokens):
            if tokens is not None and (type(tokens) is not int or not 0 <= tokens <= 2**63 - 1):
                raise InvalidAiState("Invalid token usage.")


@dataclass(frozen=True, kw_only=True)
class ToolExecution:
    id: UUID
    user_id: UUID
    run_id: UUID
    number: int
    call_id: str
    tool_name: str
    status: ExecutionStatus
    started_at: datetime
    finished_at: datetime | None = None
    error_code: ErrorCode | None = None

    def __post_init__(self) -> None:
        require_execution(self.status, self.started_at, self.finished_at, self.error_code)
        require_label(self.call_id)
        require_label(self.tool_name)
        if not 1 <= self.number <= 8:
            raise InvalidAiState("Invalid tool execution number.")


def require_execution(
    status: ExecutionStatus, started: datetime, finished: datetime | None, error: ErrorCode | None
) -> None:
    require_time(started, finished)
    if (
        status not in ("started", "succeeded", "failed", "interrupted", "rejected")
        or ((status == "started") != (finished is None))
        or (finished is not None and finished < started)
    ):
        raise InvalidAiState("Invalid execution state.")
    if error not in (
        None,
        "unavailable",
        "invalid_response",
        "timeout",
        "cancelled",
        "interrupted",
    ):
        raise InvalidAiState("Invalid execution error category.")
    if status in ("started", "succeeded", "rejected") and error is not None:
        raise InvalidAiState("Unexpected execution error category.")
