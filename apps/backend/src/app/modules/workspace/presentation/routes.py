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
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication
from app.modules.workspace.application.service import WorkspaceService
from app.modules.workspace.domain.organization import (
    InvalidWorkspaceInput,
    OrganizationKind,
    WorkspaceConflict,
    WorkspaceNotFound,
)
from app.modules.workspace.infrastructure.repository import SqlAlchemyOrganizations
from app.modules.workspace.presentation.schemas import (
    OrganizationCreate,
    OrganizationListResponse,
    OrganizationPatch,
    OrganizationResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/v1/workspace",
    tags=["workspace"],
    dependencies=[Depends(no_store), Depends(get_current_session)],
)


def get_kind(kind: Literal["collections", "tags"]) -> OrganizationKind:
    return "collection" if kind == "collections" else "tag"


Kind = Annotated[OrganizationKind, Depends(get_kind)]


def get_workspace(database: Database) -> WorkspaceService:
    return WorkspaceService(
        SqlAlchemyOrganizations(database), SqlAlchemyUserAuthentication(database)
    )


Workspace = Annotated[WorkspaceService, Depends(get_workspace)]


@router.post(
    "/{kind}",
    status_code=201,
    response_model=OrganizationResponse,
    dependencies=[Depends(require_csrf)],
)
def create_organization(
    kind: Kind,
    payload: OrganizationCreate,
    current: CurrentSession,
    database: Database,
    workspace: Workspace,
) -> OrganizationResponse:
    with database.begin():
        result = OrganizationResponse.model_validate(
            workspace.create(current.user_id, kind, **payload.model_dump())
        )
    logger.info("workspace.organization_created", extra={"user_id": str(current.user_id)})
    return result


@router.get("/{kind}", response_model=OrganizationListResponse)
def list_organizations(
    kind: Kind,
    current: CurrentSession,
    database: Database,
    workspace: Workspace,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0, le=2**31 - 1)] = 0,
) -> OrganizationListResponse:
    with database.begin():
        return OrganizationListResponse(
            items=[
                OrganizationResponse.model_validate(item)
                for item in workspace.list(current.user_id, kind, limit, offset)
            ],
            limit=limit,
            offset=offset,
        )


@router.get("/{kind}/{identifier}", response_model=OrganizationResponse)
def get_organization(
    kind: Kind, identifier: UUID, current: CurrentSession, database: Database, workspace: Workspace
) -> OrganizationResponse:
    with database.begin():
        return OrganizationResponse.model_validate(workspace.get(current.user_id, kind, identifier))


@router.patch(
    "/{kind}/{identifier}",
    response_model=OrganizationResponse,
    dependencies=[Depends(require_csrf)],
)
def update_organization(
    kind: Kind,
    identifier: UUID,
    payload: OrganizationPatch,
    current: CurrentSession,
    database: Database,
    workspace: Workspace,
) -> OrganizationResponse:
    with database.begin():
        result = OrganizationResponse.model_validate(
            workspace.update(
                current.user_id,
                kind,
                identifier,
                payload.model_dump(exclude_unset=True, exclude={"expected_version"}),
                payload.expected_version,
            )
        )
    logger.info("workspace.organization_updated", extra={"user_id": str(current.user_id)})
    return result


@router.delete("/{kind}/{identifier}", status_code=204, dependencies=[Depends(require_csrf)])
def delete_organization(
    kind: Kind,
    identifier: UUID,
    current: CurrentSession,
    database: Database,
    workspace: Workspace,
    expected_version: Annotated[int, Query(ge=1, le=2**31 - 2)],
) -> None:
    with database.begin():
        workspace.delete(current.user_id, kind, identifier, expected_version)
    logger.info("workspace.organization_deleted", extra={"user_id": str(current.user_id)})


def install_workspace(application: FastAPI) -> None:
    def workspace_error(request: Request, error: Exception) -> JSONResponse:
        if isinstance(error, WorkspaceNotFound):
            status, detail, reason = 404, "Workspace object not found.", "not_found"
        elif isinstance(error, WorkspaceConflict):
            status, detail, reason = 409, "Workspace object changed. Reload and retry.", "conflict"
        else:
            status, detail, reason = 422, "Invalid workspace input.", "invalid_input"
        log_failure(
            logger, "workspace.operation_rejected", error, level=logging.WARNING, reason=reason
        )
        return JSONResponse(
            {"detail": detail}, status_code=status, headers={"Cache-Control": "no-store"}
        )

    for error_type in (WorkspaceNotFound, WorkspaceConflict, InvalidWorkspaceInput):
        application.add_exception_handler(error_type, workspace_error)
    application.include_router(router)
