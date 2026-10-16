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
from app.modules.notes.presentation.routes import Notes
from app.modules.workspace.application.databases import DatabaseService
from app.modules.workspace.infrastructure.databases import SqlAlchemyDatabases
from app.modules.workspace.presentation.database_schemas import (
    DatabaseListResponse,
    DatabaseResponse,
    VersionRequest,
)
from app.modules.workspace.presentation.schemas import OrganizationCreate, OrganizationPatch

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/v1/workspace/databases",
    tags=["workspace databases"],
    dependencies=[Depends(no_store), Depends(get_current_session)],
)


def get_databases(database: Database, notes: Notes) -> DatabaseService:
    return DatabaseService(SqlAlchemyDatabases(database), notes)


Databases = Annotated[DatabaseService, Depends(get_databases)]


@router.post(
    "", status_code=201, response_model=DatabaseResponse, dependencies=[Depends(require_csrf)]
)
def create_database(
    payload: OrganizationCreate, current: CurrentSession, database: Database, databases: Databases
) -> DatabaseResponse:
    with database.begin():
        response = DatabaseResponse.model_validate(
            databases.create(current.user_id, **payload.model_dump())
        )
    logger.info("workspace.database_created", extra={"user_id": str(current.user_id)})
    return response


@router.get("", response_model=DatabaseListResponse)
def list_databases(
    current: CurrentSession,
    database: Database,
    databases: Databases,
    trashed: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0, le=2**31 - 1)] = 0,
) -> DatabaseListResponse:
    with database.begin():
        return DatabaseListResponse(
            items=[
                DatabaseResponse.model_validate(item)
                for item in databases.list(current.user_id, trashed, limit, offset)
            ],
            limit=limit,
            offset=offset,
        )


@router.get("/{database_id}", response_model=DatabaseResponse)
def get_database_definition(
    database_id: UUID, current: CurrentSession, database: Database, databases: Databases
) -> DatabaseResponse:
    with database.begin():
        return DatabaseResponse.model_validate(databases.get(current.user_id, database_id))


@router.patch(
    "/{database_id}", response_model=DatabaseResponse, dependencies=[Depends(require_csrf)]
)
def update_database(
    database_id: UUID,
    payload: OrganizationPatch,
    current: CurrentSession,
    database: Database,
    databases: Databases,
) -> DatabaseResponse:
    with database.begin():
        response = DatabaseResponse.model_validate(
            databases.update(
                current.user_id,
                database_id,
                payload.model_dump(exclude_unset=True, exclude={"expected_version"}),
                payload.expected_version,
            )
        )
    logger.info("workspace.database_updated", extra={"user_id": str(current.user_id)})
    return response


@router.post(
    "/{database_id}/trash", response_model=DatabaseResponse, dependencies=[Depends(require_csrf)]
)
def trash_database(
    database_id: UUID,
    payload: VersionRequest,
    current: CurrentSession,
    database: Database,
    databases: Databases,
) -> DatabaseResponse:
    with database.begin():
        response = DatabaseResponse.model_validate(
            databases.lifecycle(current.user_id, database_id, payload.expected_version)
        )
    logger.info("workspace.database_trashed", extra={"user_id": str(current.user_id)})
    return response


@router.post(
    "/{database_id}/restore", response_model=DatabaseResponse, dependencies=[Depends(require_csrf)]
)
def restore_database(
    database_id: UUID,
    payload: VersionRequest,
    current: CurrentSession,
    database: Database,
    databases: Databases,
) -> DatabaseResponse:
    with database.begin():
        response = DatabaseResponse.model_validate(
            databases.lifecycle(
                current.user_id, database_id, payload.expected_version, restore=True
            )
        )
    logger.info("workspace.database_restored", extra={"user_id": str(current.user_id)})
    return response
