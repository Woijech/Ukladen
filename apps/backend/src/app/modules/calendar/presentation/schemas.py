import re
from datetime import date, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.modules.calendar.domain.events import (
    InvalidCalendarInput,
    override_values,
    personal_values,
)
from app.modules.calendar.presentation.legacy_schemas import EventCreate as EventCreate
from app.modules.calendar.presentation.legacy_schemas import EventPatch as EventPatch
from app.modules.calendar.presentation.legacy_schemas import EventResponse as EventResponse
from app.modules.schedule.presentation.schemas import ScheduleStateResponse


def date_input(value: object) -> object:
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise InvalidCalendarInput()
    return value


CalendarDate = Annotated[date, BeforeValidator(date_input)]


class CalendarRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("starts_at", "ends_at", mode="before", check_fields=False)
    @classmethod
    def timestamp_input(cls, value: object) -> object:
        if value is not None and not (
            isinstance(value, datetime) or (isinstance(value, str) and "T" in value)
        ):
            raise InvalidCalendarInput()
        return value


class PersonalEventCreate(CalendarRequest):
    title: str = Field(min_length=1, max_length=200, strict=True)
    description: str | None = Field(default=None, max_length=10000, strict=True)
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    location: str | None = Field(default=None, max_length=500, strict=True)
    blocks_time: bool = Field(default=True, strict=True)

    @model_validator(mode="after")
    def validate_values(self) -> Self:
        personal_values(self.model_dump())
        return self


class PersonalEventPatch(CalendarRequest):
    expected_version: int = Field(ge=1, le=2**31 - 2, strict=True)
    title: str | None = Field(default=None, min_length=1, max_length=200, strict=True)
    description: str | None = Field(default=None, max_length=10000, strict=True)
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    location: str | None = Field(default=None, max_length=500, strict=True)
    blocks_time: bool | None = Field(default=None, strict=True)

    @model_validator(mode="after")
    def validate_changes(self) -> Self:
        changes = self.model_dump(exclude_unset=True, exclude={"expected_version"})
        if not changes or any(
            changes.get(name, True) is None
            for name in ("title", "starts_at", "ends_at", "blocks_time")
        ):
            raise InvalidCalendarInput()
        return self


class OverridePut(CalendarRequest):
    expected_version: int = Field(default=0, ge=0, le=2**31 - 2, strict=True)
    hidden: bool = Field(default=False, strict=True)
    skipped: bool = Field(default=False, strict=True)
    title: str | None = Field(default=None, min_length=1, max_length=200, strict=True)
    description: str | None = Field(default=None, max_length=10000, strict=True)
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    location: str | None = Field(default=None, max_length=500, strict=True)

    @model_validator(mode="after")
    def validate_values(self) -> Self:
        override_values(self.model_dump(exclude={"expected_version"}))
        return self


class PersonalEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str | None
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    location: str | None
    blocks_time: bool
    version: int
    created_at: AwareDatetime
    updated_at: AwareDatetime


class ResolvedEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: Literal["official", "personal"]
    source_event_id: UUID
    kind: Literal["lesson", "exam", "announcement", "personal"]
    title: str
    description: str | None
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    location: str | None
    blocks_time: bool
    hidden: bool
    skipped: bool
    has_override: bool
    version: int
    group_id: int | None
    subgroup: int | None
    subject: str | None
    subject_full_name: str | None
    lesson_type: str | None
    note: str | None
    rooms: tuple[str, ...]
    teacher_ids: tuple[int, ...]
    teacher_names: tuple[str, ...]


class CalendarResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    events: list[ResolvedEventResponse]
    timezone: str
    source: ScheduleStateResponse | None
    warnings: list[str]


class OverrideResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    official_event_id: UUID
    hidden: bool
    skipped: bool
    title: str | None
    description: str | None
    starts_at: AwareDatetime | None
    ends_at: AwareDatetime | None
    location: str | None
    version: int
    created_at: AwareDatetime
    updated_at: AwareDatetime


class OverrideEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    override: OverrideResponse
    source_status: Literal["active", "inactive_source", "outside_profile"]


class OverrideListResponse(BaseModel):
    items: list[OverrideEntryResponse]
    limit: int
    offset: int
