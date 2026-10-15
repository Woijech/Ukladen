from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.modules.reminders.domain.reminders import ReminderSource, ReminderStatus

MinutesBefore = Annotated[int, Field(strict=True, ge=0, le=43200)]


class ReminderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: ReminderSource
    event_id: UUID
    minutes_before: MinutesBefore = 15


class ExpectedVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: Annotated[int, Field(strict=True, ge=1)]


class ReminderPatch(ExpectedVersion):
    minutes_before: MinutesBefore


class ReminderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source: ReminderSource
    event_id: UUID
    minutes_before: int
    starts_at: AwareDatetime
    due_at: AwareDatetime
    status: ReminderStatus
    version: int
    created_at: AwareDatetime
    updated_at: AwareDatetime


class ReminderListResponse(BaseModel):
    items: list[ReminderResponse]
    limit: int
    offset: int
