from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.modules.schedule.application.storage import SyncState


class ScheduleStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    group_id: int
    group_number: str
    status: SyncState
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    error_code: str | None


class OfficialEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    group_id: int
    kind: Literal["lesson", "exam", "announcement"]
    subgroup: int
    starts_at: datetime
    ends_at: datetime
    subject: str | None
    subject_full_name: str | None
    lesson_type: str | None
    note: str | None
    rooms: list[str]
    teacher_ids: list[int]
    teacher_names: list[str]
    active: bool


class ScheduleEventsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    events: list[OfficialEventResponse]
    source: ScheduleStateResponse


class SyncAcceptedResponse(BaseModel):
    group_id: int
    status: Literal["accepted"] = "accepted"
