from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.ai.application.agent import AgentInput
from app.modules.ai.application.lifecycle import RunSnapshot
from app.modules.ai.domain.state import ErrorCode, ExecutionStatus, MessageRole, RunStatus


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def bounded_title(cls, value: str) -> str:
        return AgentInput.bounded_message(value)


class MessageSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    submission_id: UUID
    message: str = Field(min_length=1, max_length=16384)

    @field_validator("message")
    @classmethod
    def bounded_message(cls, value: str) -> str:
        return AgentInput.bounded_message(value)

    def agent_input(self, conversation_id: UUID) -> AgentInput:
        return AgentInput(conversation_id=conversation_id, message=self.message)


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    created_at: datetime
    last_user_message_at: datetime | None


class ConversationList(BaseModel):
    items: list[ConversationResponse]


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    sequence: int
    role: MessageRole
    content: str
    created_at: datetime


class MessageList(BaseModel):
    items: list[MessageResponse]


class AttemptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    number: int
    status: ExecutionStatus
    started_at: datetime
    finished_at: datetime | None
    input_tokens: int | None
    output_tokens: int | None
    error_code: ErrorCode | None


class ToolResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    number: int
    call_id: str
    tool_name: str
    status: ExecutionStatus
    started_at: datetime
    finished_at: datetime | None
    error_code: ErrorCode | None


class RunResponse(BaseModel):
    id: UUID
    conversation_id: UUID | None
    submission_id: UUID
    provider: str
    model: str
    status: RunStatus
    version: int
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None
    attempts: list[AttemptResponse]
    tools: list[ToolResponse]

    @classmethod
    def from_snapshot(cls, snapshot: RunSnapshot) -> RunResponse:
        run = snapshot.run
        return cls(
            id=run.id,
            conversation_id=run.conversation_id,
            submission_id=run.submission_id,
            provider=run.provider,
            model=run.model,
            status=run.status,
            version=run.version,
            created_at=run.created_at,
            updated_at=run.updated_at,
            finished_at=run.finished_at,
            attempts=[AttemptResponse.model_validate(item) for item in snapshot.attempts],
            tools=[ToolResponse.model_validate(item) for item in snapshot.tools],
        )
