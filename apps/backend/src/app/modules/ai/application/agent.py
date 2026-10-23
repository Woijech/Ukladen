from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from app.modules.ai.domain.state import ErrorCode


class InvalidAgentReview(ValueError):
    pass


class AgentInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    conversation_id: UUID
    message: str = Field(min_length=1, max_length=16384)

    @field_validator("message")
    @classmethod
    def bounded_message(cls, value: str) -> str:
        try:
            size = len(value.encode("utf-8"))
        except UnicodeEncodeError:
            raise ValueError("Invalid message encoding.") from None
        if size > 16384 or not value.strip() or "\x00" in value:
            raise ValueError("Message must contain text within 16 KiB UTF-8.")
        return value


class ReviewAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_name: str
    arguments: dict[str, JsonValue]


class PendingReview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    interrupt_id: str
    actions: tuple[ReviewAction, ...]


class AgentReview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    interrupt_id: str = Field(min_length=1, max_length=128)
    decisions: tuple[Literal["approve", "reject"], ...] = Field(min_length=1, max_length=8)


class ToolOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    call_id: str
    tool_name: str
    status: Literal["success", "error"]
    content: str


class AgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["completed", "interrupted", "limited", "failed"]
    answer: str | None = None
    review: PendingReview | None = None
    tools: tuple[ToolOutcome, ...] = ()
    error_code: ErrorCode | None = None


class AgentRunner(Protocol):
    """Internal execution boundary; callers must supply authorized conversation identity."""

    def run(self, request: AgentInput) -> AgentResult: ...
    def resume(self, conversation_id: UUID, review: AgentReview) -> AgentResult: ...
