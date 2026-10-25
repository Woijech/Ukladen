from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.modules.ai.application.agent import AgentInput
from app.modules.ai.application.connections import require_key
from app.modules.ai.application.lifecycle import RunSnapshot
from app.modules.ai.application.source_queries import SourceScope
from app.modules.ai.domain.pricing import PriceSnapshot
from app.modules.ai.domain.state import ErrorCode, ExecutionStatus, MessageRole, RunStatus
from app.modules.search.domain.evidence import SourceReference


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    offering_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9-]{0,63}$")
    connection_id: UUID | None = None
    demo: bool = False

    @field_validator("title")
    @classmethod
    def bounded_title(cls, value: str) -> str:
        return AgentInput.bounded_message(value)


class MessageSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    submission_id: UUID
    message: str = Field(min_length=1, max_length=16384)
    source_scope: SourceScope | None = None

    @field_validator("message")
    @classmethod
    def bounded_message(cls, value: str) -> str:
        return AgentInput.bounded_message(value)

    def agent_input(self, conversation_id: UUID) -> AgentInput:
        return AgentInput(
            conversation_id=conversation_id, message=self.message, source_scope=self.source_scope
        )


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    created_at: datetime
    last_user_message_at: datetime | None
    offering_id: str | None
    offering_version: int | None
    connection_id: UUID | None
    provider: str
    model: str


class ConversationList(BaseModel):
    items: list[ConversationResponse]


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    sequence: int
    role: MessageRole
    content: str
    created_at: datetime
    sources: tuple[SourceReference, ...] = ()


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
    offering_id: str | None
    offering_version: int | None
    connection_id: UUID | None
    price: PriceSnapshot | None = None
    estimated_cost: Decimal | None = None
    unpriced_attempts: int = 0

    @classmethod
    def from_snapshot(cls, snapshot: RunSnapshot) -> RunResponse:
        run = snapshot.run
        return cls(
            price=run.price,
            estimated_cost=snapshot.estimated_cost,
            unpriced_attempts=snapshot.unpriced_attempts,
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
            offering_id=run.offering_id,
            offering_version=run.offering_version,
            connection_id=run.connection_id,
        )


class ConnectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    label: str = Field(min_length=1, max_length=100)
    key: SecretStr = Field(repr=False)

    @field_validator("label")
    @classmethod
    def bounded_label(cls, value: str) -> str:
        return AgentInput.bounded_message(value).strip()

    @field_validator("key")
    @classmethod
    def bounded_key(cls, value: SecretStr) -> SecretStr:
        require_key(value.get_secret_value())
        return value


class ConnectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    label: str
    created_at: datetime
    disconnected_at: datetime | None
    key_mask: str = "********"


class ConnectionList(BaseModel):
    items: list[ConnectionResponse]


class PreferencesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instructions: str = Field(max_length=8192)
    expected_version: int = Field(ge=0, le=2**31 - 2)

    @field_validator("instructions")
    @classmethod
    def bounded_instructions(cls, value: str) -> str:
        from app.modules.ai.domain.preferences import AssistantPreferences

        return AssistantPreferences(value).instructions


class PreferencesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    instructions: str
    version: int


class ConversationState(BaseModel):
    conversation: ConversationResponse
    run: RunResponse | None
