from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse

from app.modules.academics.presentation.routes import no_store
from app.modules.auth.presentation.dependencies import (
    CurrentSession,
    Database,
    get_current_session,
    require_csrf,
)
from app.modules.calendar.presentation.routes import Calendar
from app.modules.reminders.application.service import ReminderService
from app.modules.reminders.domain.reminders import (
    InvalidReminderInput,
    ReminderConflict,
    ReminderNotFound,
)
from app.modules.reminders.infrastructure.repository import SqlAlchemyReminderRepository
from app.modules.reminders.presentation.schemas import (
    ExpectedVersion,
    ReminderCreate,
    ReminderListResponse,
    ReminderPatch,
    ReminderResponse,
)
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication

router = APIRouter(
    prefix="/api/v1/reminders",
    tags=["reminders"],
    dependencies=[Depends(get_current_session), Depends(no_store)],
)


def get_reminders(database: Database, calendar: Calendar) -> ReminderService:
    return ReminderService(
        SqlAlchemyReminderRepository(database), SqlAlchemyUserAuthentication(database), calendar
    )


Reminders = Annotated[ReminderService, Depends(get_reminders)]


@router.post(
    "", status_code=201, response_model=ReminderResponse, dependencies=[Depends(require_csrf)]
)
def create_reminder(
    payload: ReminderCreate, current: CurrentSession, database: Database, reminders: Reminders
) -> ReminderResponse:
    with database.begin():
        result = ReminderResponse.model_validate(
            reminders.create(current.user_id, **payload.model_dump())
        )
    return result


@router.get("", response_model=ReminderListResponse)
def list_reminders(
    current: CurrentSession,
    database: Database,
    reminders: Reminders,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0, le=2**31 - 1)] = 0,
) -> ReminderListResponse:
    with database.begin():
        return ReminderListResponse(
            items=[
                ReminderResponse.model_validate(item)
                for item in reminders.list(current.user_id, limit, offset)
            ],
            limit=limit,
            offset=offset,
        )


@router.get("/{reminder_id}", response_model=ReminderResponse)
def get_reminder(
    reminder_id: UUID, current: CurrentSession, database: Database, reminders: Reminders
) -> ReminderResponse:
    with database.begin():
        return ReminderResponse.model_validate(reminders.get(current.user_id, reminder_id))


@router.patch(
    "/{reminder_id}", response_model=ReminderResponse, dependencies=[Depends(require_csrf)]
)
def update_reminder(
    reminder_id: UUID,
    payload: ReminderPatch,
    current: CurrentSession,
    database: Database,
    reminders: Reminders,
) -> ReminderResponse:
    with database.begin():
        result = ReminderResponse.model_validate(
            reminders.update(current.user_id, reminder_id, **payload.model_dump())
        )
    return result


@router.post(
    "/{reminder_id}/cancel", response_model=ReminderResponse, dependencies=[Depends(require_csrf)]
)
def cancel_reminder(
    reminder_id: UUID,
    payload: ExpectedVersion,
    current: CurrentSession,
    database: Database,
    reminders: Reminders,
) -> ReminderResponse:
    with database.begin():
        result = ReminderResponse.model_validate(
            reminders.cancel(current.user_id, reminder_id, payload.expected_version)
        )
    return result


@router.delete("/{reminder_id}", status_code=204, dependencies=[Depends(require_csrf)])
def delete_reminder(
    reminder_id: UUID,
    current: CurrentSession,
    database: Database,
    reminders: Reminders,
    expected_version: Annotated[int, Query(ge=1)],
) -> None:
    with database.begin():
        reminders.delete(current.user_id, reminder_id, expected_version)


def install_reminders(application: FastAPI) -> None:
    def reminder_error(request: Request, error: Exception) -> JSONResponse:
        if isinstance(error, InvalidReminderInput):
            status, detail = 422, "Invalid reminder input or trigger is not in the future."
        elif isinstance(error, ReminderNotFound):
            status, detail = 404, "Reminder not found."
        else:
            status, detail = 409, "Reminder or target changed. Reload and retry."
        return JSONResponse(
            {"detail": detail}, status_code=status, headers={"Cache-Control": "no-store"}
        )

    for error in (InvalidReminderInput, ReminderNotFound, ReminderConflict):
        application.add_exception_handler(error, reminder_error)
    application.include_router(router)
