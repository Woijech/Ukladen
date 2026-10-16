import logging
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from app.modules.academics.presentation.routes import no_store
from app.modules.auth.presentation.dependencies import CurrentSession, Database, get_current_session
from app.modules.calendar.application.composition import CalendarCompositionService
from app.modules.calendar.presentation.record_dates import RecordDateResponse
from app.modules.calendar.presentation.routes import Calendar
from app.modules.calendar.presentation.schemas import CalendarDate, ResolvedEventResponse
from app.modules.schedule.presentation.schemas import ScheduleStateResponse
from app.modules.workspace.application.database_calendar import DatabaseCalendarService
from app.modules.workspace.presentation.database_views import Views

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/v1/calendar",
    tags=["calendar"],
    dependencies=[Depends(get_current_session), Depends(no_store)],
)


class CalendarDisplayResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    entries: list[
        Annotated[ResolvedEventResponse | RecordDateResponse, Field(discriminator="source")]
    ]
    timezone: str
    source: ScheduleStateResponse | None
    warnings: list[str]


@router.get("/display", response_model=CalendarDisplayResponse)
def display_calendar(
    current: CurrentSession,
    database: Database,
    calendar: Calendar,
    views: Views,
    date_from: CalendarDate,
    date_to: CalendarDate,
    database_view_ids: Annotated[list[UUID] | None, Query(max_length=20)] = None,
    include_hidden: bool = False,
    source: Literal["official", "personal"] | None = None,
) -> CalendarDisplayResponse:
    with database.begin():
        database.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        response = CalendarDisplayResponse.model_validate(
            CalendarCompositionService(calendar, DatabaseCalendarService(views)).display(
                current.user_id,
                date_from,
                date_to,
                tuple(database_view_ids or ()),
                include_hidden=include_hidden,
                source=source,
            )
        )
    logger.info(
        "calendar.display_resolved",
        extra={"user_id": str(current.user_id), "entry_count": len(response.entries)},
    )
    return response
