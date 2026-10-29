from typing import Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.modules.calendar.domain.availability import TimeInterval
from app.modules.calendar.presentation.schemas import CalendarRequest
from app.modules.schedule.presentation.schemas import ScheduleStateResponse


class IntervalInput(CalendarRequest):
    starts_at: AwareDatetime
    ends_at: AwareDatetime

    @model_validator(mode="after")
    def valid_interval(self) -> Self:
        TimeInterval(self.starts_at, self.ends_at)
        return self


class AvailabilityRequest(IntervalInput):
    windows: list[IntervalInput] = Field(default_factory=list, max_length=1024)
    candidates: list[IntervalInput] = Field(default_factory=list, max_length=1024)
    minimum_minutes: int = Field(default=15, ge=1, le=525600, strict=True)
    exclude_personal_event_id: UUID | None = None


class IntervalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    starts_at: AwareDatetime
    ends_at: AwareDatetime


class BusyEventResponse(IntervalResponse):
    id: str
    source: str
    source_event_id: UUID
    title: str
    version: int


class ConflictResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    candidate_index: int
    event_ids: list[str]


class AvailabilityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    occupied: list[IntervalResponse]
    free: list[IntervalResponse]
    events: list[BusyEventResponse]
    conflicts: list[ConflictResponse]
    timezone: str
    source: ScheduleStateResponse | None
    warnings: list[str]
    verified: bool
    snapshot: str
