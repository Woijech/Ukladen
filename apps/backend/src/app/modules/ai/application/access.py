from datetime import datetime
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.ai.application.persistence import AiRepository


class AiAccessStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    plan: str = "free"
    monthly_request_limit: int | None = Field(default=None, ge=0)
    monthly_token_limit: int | None = Field(default=None, ge=0)


class AiAccessPolicy(Protocol):
    def status(self, user_id: UUID) -> AiAccessStatus: ...
    def admit(self, user_id: UUID, repository: AiRepository, now: datetime) -> None:
        """Reserve future owner quotas in the new run's transaction or raise UsageLimited."""
        ...


class UnlimitedAiAccessPolicy:
    def status(self, user_id: UUID) -> AiAccessStatus:
        return AiAccessStatus()

    def admit(self, user_id: UUID, repository: AiRepository, now: datetime) -> None:
        pass
