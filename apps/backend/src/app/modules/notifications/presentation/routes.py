from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime, BaseModel, ConfigDict

from app.modules.academics.presentation.routes import no_store
from app.modules.auth.presentation.dependencies import (
    CurrentSession,
    Database,
    get_current_session,
    require_csrf,
)
from app.modules.notifications.application.service import NotificationService
from app.modules.notifications.domain.notifications import (
    InvalidNotificationInput,
    NotificationNotFound,
)
from app.modules.notifications.infrastructure.repository import SqlAlchemyNotificationRepository
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reminder_id: UUID
    source: Literal["personal", "official"]
    event_id: UUID
    title: str
    starts_at: AwareDatetime
    created_at: AwareDatetime
    read_at: AwareDatetime | None


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    limit: int
    offset: int


router = APIRouter(
    prefix="/api/v1/notifications",
    tags=["notifications"],
    dependencies=[Depends(get_current_session), Depends(no_store)],
)


def get_notifications(database: Database) -> NotificationService:
    return NotificationService(
        SqlAlchemyNotificationRepository(database), SqlAlchemyUserAuthentication(database)
    )


Notifications = Annotated[NotificationService, Depends(get_notifications)]


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    current: CurrentSession,
    database: Database,
    notifications: Notifications,
    unread_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0, le=2**31 - 1)] = 0,
) -> NotificationListResponse:
    with database.begin():
        return NotificationListResponse(
            items=[
                NotificationResponse.model_validate(item)
                for item in notifications.list(current.user_id, unread_only, limit, offset)
            ],
            limit=limit,
            offset=offset,
        )


@router.get("/{notification_id}", response_model=NotificationResponse)
def get_notification(
    notification_id: UUID, current: CurrentSession, database: Database, notifications: Notifications
) -> NotificationResponse:
    with database.begin():
        return NotificationResponse.model_validate(
            notifications.get(current.user_id, notification_id)
        )


@router.post(
    "/{notification_id}/read",
    response_model=NotificationResponse,
    dependencies=[Depends(require_csrf)],
)
def read_notification(
    notification_id: UUID, current: CurrentSession, database: Database, notifications: Notifications
) -> NotificationResponse:
    with database.begin():
        result = NotificationResponse.model_validate(
            notifications.mark_read(current.user_id, notification_id)
        )
    return result


def install_notifications(application: FastAPI) -> None:
    def notification_error(request: Request, error: Exception) -> JSONResponse:
        status = 404 if isinstance(error, NotificationNotFound) else 422
        detail = "Notification not found." if status == 404 else "Invalid notification input."
        return JSONResponse(
            {"detail": detail}, status_code=status, headers={"Cache-Control": "no-store"}
        )

    for error in (NotificationNotFound, InvalidNotificationInput):
        application.add_exception_handler(error, notification_error)
    application.include_router(router)
