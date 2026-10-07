from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Path, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime

from app.modules.academics.presentation.routes import no_store
from app.modules.auth.domain.errors import InvalidSession
from app.modules.auth.presentation.dependencies import (
    CurrentSession,
    Database,
    get_current_session,
    require_csrf,
)
from app.modules.calendar.application.service import PersonalEventService
from app.modules.calendar.domain.errors import EventNotFound, InvalidEventInput
from app.modules.calendar.infrastructure.repository import SqlAlchemyPersonalCalendarEventRepository
from app.modules.calendar.presentation.schemas import EventCreate, EventPatch, EventResponse
from app.modules.users.domain.profile import ProfileUnavailable
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication

router = APIRouter(
    prefix="/api/v1/calendar",
    tags=["calendar"],
    dependencies=[Depends(get_current_session), Depends(no_store)],
)

EventIdPath = Annotated[UUID, Path()]
PeriodStart = Annotated[AwareDatetime, Query()]
PeriodEnd = Annotated[AwareDatetime, Query()]


def get_events(database: Database) -> PersonalEventService:
    return PersonalEventService(
        SqlAlchemyPersonalCalendarEventRepository(database),
        SqlAlchemyUserAuthentication(database),
    )


Events = Annotated[PersonalEventService, Depends(get_events)]


def list_events(
    current: CurrentSession,
    database: Database,
    events: Events,
    starts_at: PeriodStart,
    ends_at: PeriodEnd,
) -> list[EventResponse]:
    with database.begin():
        found = events.list(current.user_id, starts_at, ends_at)
    return [EventResponse.from_event(event) for event in found]


@router.post(
    "/events",
    response_model=EventResponse,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def create_event(
    payload: EventCreate,
    current: CurrentSession,
    database: Database,
    events: Events,
    response: Response,
) -> EventResponse:
    with database.begin():
        event = events.create(current.user_id, payload.model_dump(exclude_unset=True))
    result = EventResponse.from_event(event)
    response.headers["Location"] = f"/api/v1/calendar/events/{result.id}"
    return result


@router.get("/events/{event_id}", response_model=EventResponse)
def get_event(
    event_id: EventIdPath,
    current: CurrentSession,
    database: Database,
    events: Events,
) -> EventResponse:
    with database.begin():
        event = events.get(current.user_id, event_id)
    return EventResponse.from_event(event)


@router.patch(
    "/events/{event_id}",
    response_model=EventResponse,
    dependencies=[Depends(require_csrf)],
)
def update_event(
    payload: EventPatch,
    event_id: EventIdPath,
    current: CurrentSession,
    database: Database,
    events: Events,
) -> EventResponse:
    with database.begin():
        event = events.update(current.user_id, event_id, payload.model_dump(exclude_unset=True))
    return EventResponse.from_event(event)


@router.delete(
    "/events/{event_id}",
    status_code=204,
    dependencies=[Depends(require_csrf)],
)
def delete_event(
    event_id: EventIdPath,
    current: CurrentSession,
    database: Database,
    events: Events,
) -> None:
    with database.begin():
        events.delete(current.user_id, event_id)


def install_legacy_calendar(application: FastAPI) -> None:
    # Canonical eligibility failures use the existing auth response and cookie clearing.
    application.add_exception_handler(
        ProfileUnavailable, application.exception_handlers[InvalidSession]
    )

    def calendar_error(request: Request, error: Exception) -> JSONResponse:
        if isinstance(error, InvalidEventInput):
            status, detail = 422, "Invalid calendar event."
        elif isinstance(error, EventNotFound):
            status, detail = 404, "Calendar event not found."
        else:
            status, detail = 503, "Service unavailable."
        return JSONResponse(
            {"detail": detail}, status_code=status, headers={"Cache-Control": "no-store"}
        )

    for error_type in (InvalidEventInput, EventNotFound):
        application.add_exception_handler(error_type, calendar_error)
    application.include_router(router)
