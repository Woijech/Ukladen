from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict

from app.modules.notes.presentation.schemas import PageSummary


class LinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    page_id: UUID
    source: Literal["personal", "official"]
    event_id: UUID
    created_at: AwareDatetime


class LinkedPageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    link: LinkResponse
    page: PageSummary


class EventReferenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    source: Literal["personal", "official"]
    event_id: UUID
    title: str
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    source_status: Literal["active", "inactive_source", "outside_profile"]
    hidden: bool
    skipped: bool


class LinkedEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    link: LinkResponse
    event: EventReferenceResponse


class EventPagesResponse(BaseModel):
    items: list[LinkedPageResponse]
    limit: int
    offset: int


class PageEventsResponse(BaseModel):
    items: list[LinkedEventResponse]
    limit: int
    offset: int
