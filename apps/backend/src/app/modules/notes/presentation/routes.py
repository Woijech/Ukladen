import logging
from typing import Annotated
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
from app.modules.notes.application.service import NoteService
from app.modules.notes.domain.pages import InvalidPageInput, PageConflict, PageNotFound
from app.modules.notes.infrastructure.repository import SqlAlchemyPageRepository
from app.modules.notes.presentation.schemas import (
    PageCreate,
    PageListResponse,
    PagePatch,
    PageResponse,
    PageSummary,
    VersionRequest,
)
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/v1/notes/pages",
    tags=["notes"],
    dependencies=[Depends(no_store), Depends(get_current_session)],
)


def get_notes(database: Database) -> NoteService:
    return NoteService(SqlAlchemyPageRepository(database), SqlAlchemyUserAuthentication(database))


Notes = Annotated[NoteService, Depends(get_notes)]


@router.get("", response_model=PageListResponse)
def list_pages(
    current: CurrentSession,
    database: Database,
    notes: Notes,
    parent_id: UUID | None = None,
    roots_only: bool = False,
    trashed: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0, le=2**31 - 1)] = 0,
) -> PageListResponse:
    with database.begin():
        pages = notes.list_pages(
            current.user_id,
            parent_id=parent_id,
            roots_only=roots_only,
            trashed=trashed,
            limit=limit,
            offset=offset,
        )
        return PageListResponse(
            items=[PageSummary.model_validate(page) for page in pages], limit=limit, offset=offset
        )


@router.post("", status_code=201, response_model=PageResponse, dependencies=[Depends(require_csrf)])
def create_page(
    payload: PageCreate,
    current: CurrentSession,
    database: Database,
    notes: Notes,
) -> PageResponse:
    with database.begin():
        result = PageResponse.model_validate(notes.create(current.user_id, **payload.model_dump()))
    logger.info("notes.page_created", extra={"user_id": str(current.user_id)})
    return result


@router.get("/{page_id}", response_model=PageResponse)
def get_page(
    page_id: UUID, current: CurrentSession, database: Database, notes: Notes
) -> PageResponse:
    with database.begin():
        return PageResponse.model_validate(notes.get(current.user_id, page_id))


@router.patch("/{page_id}", response_model=PageResponse, dependencies=[Depends(require_csrf)])
def update_page(
    page_id: UUID,
    payload: PagePatch,
    current: CurrentSession,
    database: Database,
    notes: Notes,
) -> PageResponse:
    with database.begin():
        result = PageResponse.model_validate(
            notes.update(
                current.user_id,
                page_id,
                payload.model_dump(exclude_unset=True, exclude={"expected_version"}),
                payload.expected_version,
            )
        )
    logger.info("notes.page_updated", extra={"user_id": str(current.user_id)})
    return result


@router.post("/{page_id}/trash", response_model=PageResponse, dependencies=[Depends(require_csrf)])
def trash_page(
    page_id: UUID,
    payload: VersionRequest,
    current: CurrentSession,
    database: Database,
    notes: Notes,
) -> PageResponse:
    with database.begin():
        result = PageResponse.model_validate(
            notes.trash(current.user_id, page_id, payload.expected_version)
        )
    logger.info("notes.page_trashed", extra={"user_id": str(current.user_id)})
    return result


@router.post(
    "/{page_id}/restore", response_model=PageResponse, dependencies=[Depends(require_csrf)]
)
def restore_page(
    page_id: UUID,
    payload: VersionRequest,
    current: CurrentSession,
    database: Database,
    notes: Notes,
) -> PageResponse:
    with database.begin():
        result = PageResponse.model_validate(
            notes.restore(current.user_id, page_id, payload.expected_version)
        )
    logger.info("notes.page_restored", extra={"user_id": str(current.user_id)})
    return result


def install_notes(application: FastAPI) -> None:
    def notes_error(request: Request, error: Exception) -> JSONResponse:
        if isinstance(error, InvalidPageInput):
            status, detail, reason = 422, "Invalid page input.", "invalid_input"
        elif isinstance(error, PageNotFound):
            status, detail, reason = 404, "Page not found.", "not_found"
        else:
            status, detail, reason = (
                409,
                "Page changed or hierarchy operation is unavailable.",
                "conflict",
            )
        log_failure(logger, "notes.operation_rejected", error, level=logging.WARNING, reason=reason)
        return JSONResponse(
            {"detail": detail}, status_code=status, headers={"Cache-Control": "no-store"}
        )

    for error_type in (InvalidPageInput, PageNotFound, PageConflict):
        application.add_exception_handler(error_type, notes_error)
    application.include_router(router)
