from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.modules.academics.presentation.routes import no_store
from app.modules.auth.presentation.dependencies import (
    CurrentSession,
    Database,
    get_current_session,
    require_csrf,
)
from app.modules.calendar.application.calendars import PersonalCalendarService
from app.modules.calendar.domain.calendars import CalendarVisibility
from app.modules.calendar.infrastructure.calendars import SqlAlchemyPersonalCalendars
from app.modules.users.infrastructure.repository import SqlAlchemyProfileRepository

router = APIRouter(
    prefix="/api/v1/calendar",
    tags=["calendar"],
    dependencies=[Depends(get_current_session), Depends(no_store)],
)


def service(database: Database) -> PersonalCalendarService:
    return PersonalCalendarService(
        SqlAlchemyPersonalCalendars(database), SqlAlchemyProfileRepository(database)
    )


Calendars = Annotated[PersonalCalendarService, Depends(service)]


class CalendarInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100, strict=True)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$", strict=True)


class VersionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1, le=2**31 - 2, strict=True)


class CalendarPatch(CalendarInput, VersionInput):
    pass


class CalendarResponse(CalendarInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    version: int
    created_at: datetime
    updated_at: datetime


class CalendarList(BaseModel):
    items: list[CalendarResponse]


class Visibility(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    version: int = Field(ge=0, le=2**31 - 2, strict=True)
    default_visible: bool = Field(strict=True)
    hidden_calendar_ids: tuple[UUID, ...] = Field(max_length=100)
    hidden_lesson_types: tuple[Literal["ЛК", "ЛР", "ПЗ", "other"], ...] = Field(max_length=4)


@router.get("/calendars", response_model=CalendarList)
def list_calendars(
    current: CurrentSession, database: Database, calendars: Calendars
) -> CalendarList:
    with database.begin():
        return CalendarList(
            items=[CalendarResponse.model_validate(c) for c in calendars.list(current.user_id)]
        )


@router.post(
    "/calendars",
    response_model=CalendarResponse,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def create_calendar(
    payload: CalendarInput, current: CurrentSession, database: Database, calendars: Calendars
) -> CalendarResponse:
    with database.begin():
        return CalendarResponse.model_validate(
            calendars.write(current.user_id, payload.name, payload.color)
        )


@router.patch(
    "/calendars/{identifier}", response_model=CalendarResponse, dependencies=[Depends(require_csrf)]
)
def edit_calendar(
    identifier: UUID,
    payload: CalendarPatch,
    current: CurrentSession,
    database: Database,
    calendars: Calendars,
) -> CalendarResponse:
    with database.begin():
        return CalendarResponse.model_validate(
            calendars.write(
                current.user_id, payload.name, payload.color, identifier, payload.expected_version
            )
        )


@router.delete("/calendars/{identifier}", status_code=204, dependencies=[Depends(require_csrf)])
def delete_calendar(
    identifier: UUID,
    payload: VersionInput,
    current: CurrentSession,
    database: Database,
    calendars: Calendars,
) -> None:
    with database.begin():
        calendars.delete(current.user_id, identifier, payload.expected_version)


@router.get("/visibility", response_model=Visibility)
def read_visibility(
    current: CurrentSession, database: Database, calendars: Calendars
) -> Visibility:
    with database.begin():
        return Visibility.model_validate(calendars.visibility(current.user_id))


@router.put("/visibility", response_model=Visibility, dependencies=[Depends(require_csrf)])
def write_visibility(
    payload: Visibility, current: CurrentSession, database: Database, calendars: Calendars
) -> Visibility:
    with database.begin():
        return Visibility.model_validate(
            calendars.set_visibility(current.user_id, CalendarVisibility(**payload.model_dump()))
        )
