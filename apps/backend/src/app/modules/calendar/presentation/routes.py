import logging
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse

from app.core.logging import log_failure
from app.modules.academics.presentation.routes import Academics, no_store
from app.modules.auth.presentation.dependencies import (
    CurrentSession,
    Database,
    get_current_session,
    require_csrf,
)
from app.modules.calendar.application.service import CalendarService
from app.modules.calendar.domain.events import (
    CalendarConflict,
    CalendarEventNotFound,
    InvalidCalendarInput,
)
from app.modules.calendar.infrastructure.repository import SqlAlchemyCalendarRepository
from app.modules.calendar.presentation.legacy_routes import (
    get_events as get_events,
    install_legacy_calendar,
)
from app.modules.calendar.presentation.schemas import (
    CalendarResponse,
    OverrideEntryResponse,
    OverrideListResponse,
    OverridePut,
    OverrideResponse,
    PersonalEventCreate,
    PersonalEventPatch,
    PersonalEventResponse,
)
from app.modules.schedule.application.queries import ScheduleQueryService
from app.modules.schedule.infrastructure.storage import SqlAlchemyScheduleStore
from app.modules.users.infrastructure.repository import SqlAlchemyProfileRepository

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/v1/calendar",
    tags=["calendar"],
    dependencies=[Depends(get_current_session), Depends(no_store)],
)


def get_calendar_service(
    request: Request, database: Database, academics: Academics
) -> CalendarService:
    return CalendarService(
        SqlAlchemyCalendarRepository(database),
        SqlAlchemyProfileRepository(database),
        academics,
        ScheduleQueryService(
            SqlAlchemyScheduleStore(request.app.state.session_factory, read_session=database)
        ),
        stale_after_seconds=request.app.state.settings.schedule_sync_interval_seconds,
    )


Calendar = Annotated[CalendarService, Depends(get_calendar_service)]


@router.get("/events", response_model=CalendarResponse)
def get_calendar(
    current: CurrentSession,
    database: Database,
    calendar: Calendar,
    date_from: date,
    date_to: date,
    include_hidden: bool = False,
    source: Literal["official", "personal"] | None = None,
) -> CalendarResponse:
    with database.begin():
        database.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        result = calendar.get_calendar(
            current.user_id, date_from, date_to, include_hidden=include_hidden, source=source
        )
        response = CalendarResponse.model_validate(result)
    logger.info(
        "calendar.resolved",
        extra={
            "user_id": str(current.user_id),
            "event_count": len(result.events),
            "state": result.source.status if result.source else "not_selected",
        },
    )
    return response


@router.post(
    "/personal-events",
    status_code=201,
    response_model=PersonalEventResponse,
    dependencies=[Depends(require_csrf)],
)
def create_personal_event(
    payload: PersonalEventCreate, current: CurrentSession, database: Database, calendar: Calendar
) -> PersonalEventResponse:
    with database.begin():
        result = PersonalEventResponse.model_validate(
            calendar.create_personal_event(current.user_id, payload.model_dump())
        )
    logger.info("calendar.personal_event_created", extra={"user_id": str(current.user_id)})
    return result


@router.get("/personal-events/{event_id}", response_model=PersonalEventResponse)
def get_personal_event(
    event_id: UUID, current: CurrentSession, database: Database, calendar: Calendar
) -> PersonalEventResponse:
    with database.begin():
        return PersonalEventResponse.model_validate(
            calendar.get_personal_event(current.user_id, event_id)
        )


@router.patch(
    "/personal-events/{event_id}",
    response_model=PersonalEventResponse,
    dependencies=[Depends(require_csrf)],
)
def update_personal_event(
    event_id: UUID,
    payload: PersonalEventPatch,
    current: CurrentSession,
    database: Database,
    calendar: Calendar,
) -> PersonalEventResponse:
    with database.begin():
        result = PersonalEventResponse.model_validate(
            calendar.update_personal_event(
                current.user_id,
                event_id,
                payload.model_dump(exclude_unset=True, exclude={"expected_version"}),
                payload.expected_version,
            )
        )
    logger.info("calendar.personal_event_updated", extra={"user_id": str(current.user_id)})
    return result


@router.delete("/personal-events/{event_id}", status_code=204, dependencies=[Depends(require_csrf)])
def delete_personal_event(
    event_id: UUID, current: CurrentSession, database: Database, calendar: Calendar
) -> None:
    with database.begin():
        calendar.delete_personal_event(current.user_id, event_id)
    logger.info("calendar.personal_event_deleted", extra={"user_id": str(current.user_id)})


@router.get("/overrides", response_model=OverrideListResponse)
def list_overrides(
    current: CurrentSession,
    database: Database,
    calendar: Calendar,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0, le=2**31 - 1)] = 0,
) -> OverrideListResponse:
    with database.begin():
        database.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        return OverrideListResponse(
            items=[
                OverrideEntryResponse.model_validate(item)
                for item in calendar.list_overrides(current.user_id, limit, offset)
            ],
            limit=limit,
            offset=offset,
        )


@router.put(
    "/overrides/{official_event_id}",
    response_model=OverrideResponse,
    dependencies=[Depends(require_csrf)],
)
def set_override(
    official_event_id: UUID,
    payload: OverridePut,
    current: CurrentSession,
    database: Database,
    calendar: Calendar,
) -> OverrideResponse:
    with database.begin():
        result = OverrideResponse.model_validate(
            calendar.set_override(
                current.user_id,
                official_event_id,
                payload.model_dump(exclude={"expected_version"}),
                payload.expected_version,
            )
        )
    logger.info("calendar.override_saved", extra={"user_id": str(current.user_id)})
    return result


@router.delete(
    "/overrides/{official_event_id}", status_code=204, dependencies=[Depends(require_csrf)]
)
def delete_override(
    official_event_id: UUID, current: CurrentSession, database: Database, calendar: Calendar
) -> None:
    with database.begin():
        calendar.delete_override(current.user_id, official_event_id)
    logger.info("calendar.override_deleted", extra={"user_id": str(current.user_id)})


def install_calendar(application: FastAPI) -> None:
    def calendar_error(request: Request, error: Exception) -> JSONResponse:
        if isinstance(error, InvalidCalendarInput):
            status, detail, reason = 422, "Invalid calendar input or date range.", "invalid_input"
        elif isinstance(error, CalendarEventNotFound):
            status, detail, reason = 404, "Calendar event or override not found.", "not_found"
        else:
            status, detail, reason = 409, "Calendar changed. Reload and retry.", "conflict"
        log_failure(
            logger, "calendar.operation_rejected", error, level=logging.WARNING, reason=reason
        )
        return JSONResponse(
            {"detail": detail}, status_code=status, headers={"Cache-Control": "no-store"}
        )

    for error_type in (InvalidCalendarInput, CalendarEventNotFound, CalendarConflict):
        application.add_exception_handler(error_type, calendar_error)
    application.include_router(router)
    install_legacy_calendar(application)
