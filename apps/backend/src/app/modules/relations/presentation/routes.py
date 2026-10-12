import logging
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse

from app.core.logging import log_failure
from app.modules.academics.presentation.routes import no_store
from app.modules.auth.presentation.dependencies import (
    CurrentSession,
    Database,
    get_current_session,
    require_csrf,
)
from app.modules.calendar.presentation.routes import Calendar
from app.modules.notes.presentation.routes import Notes
from app.modules.notes.presentation.schemas import PageCreate
from app.modules.relations.application.service import RelationService
from app.modules.relations.domain.links import InvalidRelationInput, RelationNotFound
from app.modules.relations.infrastructure.repository import SqlAlchemyCalendarPageLinks
from app.modules.relations.presentation.schemas import (
    EventPagesResponse,
    LinkedEventResponse,
    LinkedPageResponse,
    PageEventsResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/v1/relations",
    tags=["relations"],
    dependencies=[Depends(no_store), Depends(get_current_session)],
)


def get_relations(database: Database, notes: Notes, calendar: Calendar) -> RelationService:
    return RelationService(SqlAlchemyCalendarPageLinks(database), notes, calendar)


Relations = Annotated[RelationService, Depends(get_relations)]


@router.put(
    "/calendar-events/{source}/{event_id}/pages/{page_id}",
    response_model=LinkedPageResponse,
    dependencies=[Depends(require_csrf)],
)
def link_page(
    source: Literal["personal", "official"],
    event_id: UUID,
    page_id: UUID,
    current: CurrentSession,
    database: Database,
    relations: Relations,
) -> LinkedPageResponse:
    with database.begin():
        result = LinkedPageResponse.model_validate(
            relations.link(current.user_id, source, event_id, page_id)
        )
    logger.info("relations.page_linked", extra={"user_id": str(current.user_id)})
    return result


@router.post(
    "/calendar-events/{source}/{event_id}/pages",
    status_code=201,
    response_model=LinkedPageResponse,
    dependencies=[Depends(require_csrf)],
)
def create_linked_page(
    source: Literal["personal", "official"],
    event_id: UUID,
    payload: PageCreate,
    current: CurrentSession,
    database: Database,
    relations: Relations,
) -> LinkedPageResponse:
    with database.begin():
        result = LinkedPageResponse.model_validate(
            relations.create_linked_page(current.user_id, source, event_id, **payload.model_dump())
        )
    logger.info("relations.linked_page_created", extra={"user_id": str(current.user_id)})
    return result


@router.delete(
    "/calendar-events/{source}/{event_id}/pages/{page_id}",
    status_code=204,
    dependencies=[Depends(require_csrf)],
)
def unlink_page(
    source: Literal["personal", "official"],
    event_id: UUID,
    page_id: UUID,
    current: CurrentSession,
    database: Database,
    relations: Relations,
) -> None:
    with database.begin():
        relations.unlink(current.user_id, source, event_id, page_id)
    logger.info("relations.page_unlinked", extra={"user_id": str(current.user_id)})


@router.get("/calendar-events/{source}/{event_id}/pages", response_model=EventPagesResponse)
def event_pages(
    source: Literal["personal", "official"],
    event_id: UUID,
    current: CurrentSession,
    database: Database,
    relations: Relations,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0, le=2**31 - 1)] = 0,
) -> EventPagesResponse:
    with database.begin():
        database.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        return EventPagesResponse(
            items=[
                LinkedPageResponse.model_validate(item)
                for item in relations.event_pages(current.user_id, source, event_id, limit, offset)
            ],
            limit=limit,
            offset=offset,
        )


@router.get("/pages/{page_id}/calendar-events", response_model=PageEventsResponse)
def page_events(
    page_id: UUID,
    current: CurrentSession,
    database: Database,
    relations: Relations,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0, le=2**31 - 1)] = 0,
) -> PageEventsResponse:
    with database.begin():
        database.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        return PageEventsResponse(
            items=[
                LinkedEventResponse.model_validate(item)
                for item in relations.page_events(current.user_id, page_id, limit, offset)
            ],
            limit=limit,
            offset=offset,
        )


def install_relations(application: FastAPI) -> None:
    def relation_error(request: Request, error: Exception) -> JSONResponse:
        status = 404 if isinstance(error, RelationNotFound) else 422
        detail = "Relation not found." if status == 404 else "Invalid relation input."
        log_failure(
            logger,
            "relations.operation_rejected",
            error,
            level=logging.WARNING,
            reason="not_found" if status == 404 else "invalid_input",
        )
        return JSONResponse(
            {"detail": detail}, status_code=status, headers={"Cache-Control": "no-store"}
        )

    application.add_exception_handler(RelationNotFound, relation_error)
    application.add_exception_handler(InvalidRelationInput, relation_error)
    application.include_router(router)
