from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.modules.ai.application.persistence import AiRepository
from app.modules.ai.application.recovery import stop_run
from app.modules.ai.domain.connections import (
    ConnectionUnavailable,
    ModelSelection,
    PersonalConnection,
)
from app.modules.ai.domain.pricing import PriceSnapshot
from app.modules.ai.domain.state import AiNotFound, Conversation, InvalidAiState, Run


def require_key(value: str) -> str:
    if not 16 <= len(value) <= 1024 or any(not 33 <= ord(c) <= 126 for c in value):
        raise ValueError("Invalid API credential.")
    return value


class ModelOffering(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    version: int = Field(ge=1, le=2**31 - 1)
    name: str = Field(min_length=1, max_length=100)
    provider: Literal["openrouter"] = "openrouter"
    model: str = Field(pattern=r"^[a-z0-9-]+/[a-zA-Z0-9._:-]{1,100}$")
    tools: bool = False
    structured_output: bool = False
    streaming: bool = True
    free_only: bool = False
    personal_allowed: bool = True
    requests_per_minute: int = Field(default=10, ge=1, le=1000)
    # shortcut: bound serialized bytes until a verified per-model tokenizer is available.
    max_input_bytes: int = Field(default=6000, ge=256, le=65536)
    max_output_tokens: int = Field(default=2048, ge=1, le=2048)
    price: PriceSnapshot | None = None
    is_default: bool = False


class ModelOption(ModelOffering):
    available: bool = True
    operator_available: bool = True


class ConnectionConfiguration(Protocol):
    def offerings(self, user_id: UUID) -> Sequence[ModelOffering]: ...
    def model_options(self, user_id: UUID) -> Sequence[ModelOption]: ...
    def offering(self, user_id: UUID, offering_id: str) -> ModelOffering: ...
    def operator_key(self, offering_id: str) -> str: ...
    def quota_scope(self, offering_id: str) -> str: ...
    def encrypt(self, user_id: UUID, connection_id: UUID, key: str) -> tuple[str, bytes]: ...
    def decrypt(self, connection: PersonalConnection) -> str: ...


class ConnectionAccess:
    def __init__(self, configuration: ConnectionConfiguration) -> None:
        self.configuration = configuration

    def select(
        self, repository: AiRepository, user_id: UUID, offering_id: str, connection_id: UUID | None
    ) -> tuple[ModelSelection, ModelOffering]:
        offering = self.configuration.offering(user_id, offering_id)
        selection = ModelSelection(
            offering_id=offering.id, offering_version=offering.version, connection_id=connection_id
        )
        self.check(repository, user_id, selection, datetime.now(UTC))
        return selection, offering

    def check(
        self,
        repository: AiRepository,
        user_id: UUID,
        selection: ModelSelection | Conversation | Run,
        now: datetime,
        *,
        admit: bool = False,
    ) -> tuple[ModelOffering, str]:
        if selection.offering_id is None:
            raise ConnectionUnavailable("No real model is selected.")
        offering = self.configuration.offering(user_id, selection.offering_id)
        if offering.version != selection.offering_version or (
            isinstance(selection, (Run, Conversation))
            and (selection.provider, selection.model) != (offering.provider, offering.model)
        ):
            raise ConnectionUnavailable("Model profile changed; create a new chat.")
        if selection.connection_id is not None:
            if not offering.personal_allowed:
                raise ConnectionUnavailable("Personal connection is not supported.")
            connection = repository.get_connection(user_id, selection.connection_id)
            if connection is None:
                raise AiNotFound()
            if connection.disconnected_at is not None:
                raise ConnectionUnavailable("Connection is disconnected.")
            key = self.configuration.decrypt(connection)
            scope = f"personal:{connection.id}"
        else:
            key = self.configuration.operator_key(offering.id)
            scope = self.configuration.quota_scope(offering.id)
        if admit:
            repository.admit_connection(scope, offering.requests_per_minute, now)
        return offering, key

    def create(
        self, repository: AiRepository, user_id: UUID, label: str, key: str, now: datetime
    ) -> PersonalConnection:
        if len(repository.connections(user_id)) >= 20:
            raise InvalidAiState("At most 20 retained personal connections are supported.")
        identifier = uuid4()
        key_id, ciphertext = self.configuration.encrypt(user_id, identifier, key)
        connection = PersonalConnection(
            id=identifier,
            user_id=user_id,
            label=label,
            created_at=now,
            encrypted_key=ciphertext,
            encryption_key_id=key_id,
        )
        repository.save_connection(connection)
        return connection

    def disconnect(
        self, repository: AiRepository, user_id: UUID, connection_id: UUID, now: datetime
    ) -> None:
        connection = repository.get_connection(user_id, connection_id)
        if connection is None:
            raise AiNotFound()
        if connection.disconnected_at is None:
            repository.save_connection(
                replace(connection, encrypted_key=None, encryption_key_id=None, disconnected_at=now)
            )
        for run in repository.connection_runs(user_id, connection_id):
            stop_run(repository, run, now, status="cancelled", error="cancelled")

    def rotate(self, repository: AiRepository, user_id: UUID, connection_id: UUID) -> None:
        connection = repository.get_connection(user_id, connection_id)
        if connection is None:
            raise AiNotFound()
        if connection.disconnected_at is not None:
            raise ConnectionUnavailable("Connection is disconnected.")
        key = self.configuration.decrypt(connection)
        key_id, ciphertext = self.configuration.encrypt(user_id, connection_id, key)
        repository.save_connection(
            replace(connection, encryption_key_id=key_id, encrypted_key=ciphertext)
        )
