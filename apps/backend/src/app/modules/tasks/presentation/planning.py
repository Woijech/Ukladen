from dataclasses import asdict
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.modules.academics.presentation.routes import no_store
from app.modules.auth.presentation.dependencies import (
    CurrentSession,
    Database,
    get_current_session,
    require_csrf,
)
from app.modules.calendar.application.availability import CalendarAvailabilityService
from app.modules.calendar.presentation.availability_schemas import (
    AvailabilityResponse,
    IntervalInput,
)
from app.modules.calendar.presentation.routes import Calendar
from app.modules.tasks.application.planning import PlanningService
from app.modules.tasks.domain.planning import WeeklyWindow, WorkPreferences
from app.modules.tasks.infrastructure.planning import SqlAlchemyPlanning
from app.modules.tasks.presentation.routes import Tasks

router = APIRouter(
    prefix="/api/v1/tasks/planning",
    tags=["tasks"],
    dependencies=[Depends(get_current_session), Depends(no_store)],
)


def get_planning(database: Database, tasks: Tasks, calendar: Calendar) -> PlanningService:
    repository = SqlAlchemyPlanning(database)
    return PlanningService(tasks, repository, CalendarAvailabilityService(calendar, repository))


Planning = Annotated[PlanningService, Depends(get_planning)]


class WindowInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    weekday: int = Field(ge=0, le=6, strict=True)
    start_minute: int = Field(ge=0, le=1439, strict=True)
    end_minute: int = Field(ge=1, le=1440, strict=True)


class PreferencesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0, le=2**31 - 2, strict=True)
    windows: list[WindowInput] = Field(max_length=28)
    session_minutes: int = Field(default=45, ge=15, le=240, strict=True)
    break_minutes: int = Field(default=15, ge=0, le=120, strict=True)


class PreferencesResponse(BaseModel):
    version: int
    windows: list[WindowInput]
    session_minutes: int
    break_minutes: int


class SessionCheck(IntervalInput):
    task_id: UUID
    session_id: UUID | None = None


class SessionSave(SessionCheck):
    snapshot: str = Field(min_length=64, max_length=64)
    expected_version: int | None = Field(default=None, ge=1, le=2**31 - 2, strict=True)
    pinned: bool = Field(default=False, strict=True)
    acknowledge_conflicts: bool = Field(default=False, strict=True)


class SessionChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1, le=2**31 - 2, strict=True)
    pinned: bool | None = Field(default=None, strict=True)
    cancel: bool = Field(default=False, strict=True)


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    task_id: UUID
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    pinned: bool
    cancelled: bool
    version: int


@router.get("/preferences", response_model=PreferencesResponse)
def preferences(
    current: CurrentSession, database: Database, planning: Planning
) -> PreferencesResponse:
    with database.begin():
        return PreferencesResponse.model_validate(asdict(planning.preferences(current.user_id)))


@router.put(
    "/preferences", response_model=PreferencesResponse, dependencies=[Depends(require_csrf)]
)
def save_preferences(
    payload: PreferencesInput, current: CurrentSession, database: Database, planning: Planning
) -> PreferencesResponse:
    with database.begin():
        result = planning.save_preferences(
            current.user_id,
            WorkPreferences(
                windows=tuple(WeeklyWindow(**item.model_dump()) for item in payload.windows),
                session_minutes=payload.session_minutes,
                break_minutes=payload.break_minutes,
            ),
            payload.expected_version,
        )
        return PreferencesResponse.model_validate(asdict(result))


@router.get("/sessions", response_model=list[SessionResponse])
def sessions(
    starts_at: AwareDatetime,
    ends_at: AwareDatetime,
    current: CurrentSession,
    database: Database,
    planning: Planning,
) -> list[SessionResponse]:
    with database.begin():
        return [
            SessionResponse.model_validate(item)
            for item in planning.sessions(current.user_id, starts_at, ends_at)
        ]


@router.post(
    "/sessions/check", response_model=AvailabilityResponse, dependencies=[Depends(require_csrf)]
)
def check_session(
    payload: SessionCheck, current: CurrentSession, database: Database, planning: Planning
) -> AvailabilityResponse:
    with database.begin():
        database.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        return AvailabilityResponse.model_validate(
            planning.check_session(current.user_id, **payload.model_dump())
        )


@router.post(
    "/sessions",
    response_model=SessionResponse,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def save_session(
    payload: SessionSave, current: CurrentSession, database: Database, planning: Planning
) -> SessionResponse:
    with database.begin():
        return SessionResponse.model_validate(
            planning.save_session(current.user_id, **payload.model_dump())
        )


@router.patch(
    "/sessions/{session_id}", response_model=SessionResponse, dependencies=[Depends(require_csrf)]
)
def change_session(
    session_id: UUID,
    payload: SessionChange,
    current: CurrentSession,
    database: Database,
    planning: Planning,
) -> SessionResponse:
    with database.begin():
        return SessionResponse.model_validate(
            planning.change_session(current.user_id, session_id, **payload.model_dump())
        )
