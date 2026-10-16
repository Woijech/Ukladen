import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.modules.academics.presentation.routes import no_store
from app.modules.auth.presentation.dependencies import (
    CurrentSession,
    Database,
    get_current_session,
    require_csrf,
)
from app.modules.calendar.presentation.routes import Calendar
from app.modules.calendar.presentation.schemas import CalendarDate, CalendarResponse
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication
from app.modules.workspace.application.calendar_views import CalendarViewService
from app.modules.workspace.application.service import WorkspaceService
from app.modules.workspace.infrastructure.calendar_views import SqlAlchemyCalendarViews
from app.modules.workspace.infrastructure.repository import (
    SqlAlchemyMemberships,
    SqlAlchemyOrganizations,
)
from app.modules.workspace.presentation.schemas import (
    CalendarViewCreate,
    CalendarViewListResponse,
    CalendarViewPatch,
    CalendarViewResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/v1/workspace/calendar-views",
    tags=["workspace"],
    dependencies=[Depends(no_store), Depends(get_current_session)],
)


def get_calendar_views(database: Database, calendar: Calendar) -> CalendarViewService:
    organizations = WorkspaceService(
        SqlAlchemyOrganizations(database), SqlAlchemyUserAuthentication(database)
    )
    return CalendarViewService(
        SqlAlchemyCalendarViews(database), organizations, SqlAlchemyMemberships(database), calendar
    )


Views = Annotated[CalendarViewService, Depends(get_calendar_views)]


@router.post(
    "", status_code=201, response_model=CalendarViewResponse, dependencies=[Depends(require_csrf)]
)
def create_view(
    payload: CalendarViewCreate, current: CurrentSession, database: Database, views: Views
) -> CalendarViewResponse:
    with database.begin():
        response = CalendarViewResponse.model_validate(
            views.create(current.user_id, payload.model_dump())
        )
    logger.info("workspace.calendar_view_created", extra={"user_id": str(current.user_id)})
    return response


@router.get("", response_model=CalendarViewListResponse)
def list_views(
    current: CurrentSession,
    database: Database,
    views: Views,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0, le=2**31 - 1)] = 0,
) -> CalendarViewListResponse:
    with database.begin():
        return CalendarViewListResponse(
            items=[
                CalendarViewResponse.model_validate(item)
                for item in views.list(current.user_id, limit, offset)
            ],
            limit=limit,
            offset=offset,
        )


@router.get("/{identifier}", response_model=CalendarViewResponse)
def get_view(
    identifier: UUID, current: CurrentSession, database: Database, views: Views
) -> CalendarViewResponse:
    with database.begin():
        return CalendarViewResponse.model_validate(views.get(current.user_id, identifier))


@router.patch(
    "/{identifier}", response_model=CalendarViewResponse, dependencies=[Depends(require_csrf)]
)
def update_view(
    identifier: UUID,
    payload: CalendarViewPatch,
    current: CurrentSession,
    database: Database,
    views: Views,
) -> CalendarViewResponse:
    with database.begin():
        response = CalendarViewResponse.model_validate(
            views.update(
                current.user_id,
                identifier,
                payload.model_dump(exclude_unset=True, exclude={"expected_version"}),
                payload.expected_version,
            )
        )
    logger.info("workspace.calendar_view_updated", extra={"user_id": str(current.user_id)})
    return response


@router.delete("/{identifier}", status_code=204, dependencies=[Depends(require_csrf)])
def delete_view(
    identifier: UUID,
    current: CurrentSession,
    database: Database,
    views: Views,
    expected_version: Annotated[int, Query(ge=1, le=2**31 - 2)],
) -> None:
    with database.begin():
        views.delete(current.user_id, identifier, expected_version)
    logger.info("workspace.calendar_view_deleted", extra={"user_id": str(current.user_id)})


@router.get("/{identifier}/events", response_model=CalendarResponse)
def view_events(
    identifier: UUID,
    date_from: CalendarDate,
    date_to: CalendarDate,
    current: CurrentSession,
    database: Database,
    views: Views,
) -> CalendarResponse:
    with database.begin():
        database.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        response = CalendarResponse.model_validate(
            views.events(current.user_id, identifier, date_from, date_to)
        )
    logger.info(
        "workspace.calendar_view_resolved",
        extra={"user_id": str(current.user_id), "event_count": len(response.events)},
    )
    return response
