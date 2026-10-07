from typing import Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.modules.calendar.domain.events import (
    DESCRIPTION_MAX_LENGTH,
    TITLE_MAX_LENGTH,
    PersonalCalendarEvent,
    normalize_event_changes,
)


class EventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=TITLE_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    is_busy: bool = True

    @field_validator("title", "description", mode="before")
    @classmethod
    def trim_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_event(self) -> Self:
        normalize_event_changes(self.model_dump(exclude_unset=True))
        return self


class EventPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=TITLE_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    is_busy: bool | None = None

    @field_validator("title", "description", mode="before")
    @classmethod
    def trim_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_changes(self) -> Self:
        normalize_event_changes(self.model_dump(exclude_unset=True))
        return self


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str | None
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    is_busy: bool
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @classmethod
    def from_event(cls, event: PersonalCalendarEvent) -> Self:
        return cls.model_validate(event)
