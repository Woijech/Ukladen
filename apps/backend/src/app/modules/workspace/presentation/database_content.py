import logging
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.modules.academics.presentation.routes import no_store
from app.modules.auth.presentation.dependencies import (
    CurrentSession,
    Database,
    get_current_session,
    require_csrf,
)
from app.modules.workspace.application.database_content import DatabaseContentService
from app.modules.workspace.infrastructure.database_content import SqlAlchemyDatabaseContent
from app.modules.workspace.presentation.database_schemas import (
    PropertyCreate,
    PropertyListResponse,
    PropertyPatch,
    PropertyResponse,
    PropertyResultResponse,
    PropertyVersionRequest,
    RecordCreate,
    RecordListResponse,
    RecordPatch,
    RecordResultResponse,
    VersionRequest,
)
from app.modules.workspace.presentation.databases import Databases

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/v1/workspace/databases",
    tags=["workspace databases"],
    dependencies=[Depends(no_store), Depends(get_current_session)],
)
page_router = APIRouter(
    prefix="/api/v1/workspace/pages",
    tags=["workspace databases"],
    dependencies=[Depends(no_store), Depends(get_current_session)],
)


def get_content(database: Database, databases: Databases) -> DatabaseContentService:
    return DatabaseContentService(SqlAlchemyDatabaseContent(database), databases)


Content = Annotated[DatabaseContentService, Depends(get_content)]


@router.post(
    "/{database_id}/properties",
    status_code=201,
    response_model=PropertyResultResponse,
    dependencies=[Depends(require_csrf)],
)
def create_property(
    database_id: UUID,
    payload: PropertyCreate,
    current: CurrentSession,
    database: Database,
    content: Content,
) -> PropertyResultResponse:
    with database.begin():
        response = PropertyResultResponse.model_validate(
            content.create_property(current.user_id, database_id, **payload.model_dump())
        )
    logger.info("workspace.database_property_created", extra={"user_id": str(current.user_id)})
    return response


@router.get("/{database_id}/properties", response_model=PropertyListResponse)
def list_properties(
    database_id: UUID,
    current: CurrentSession,
    database: Database,
    content: Content,
    trashed: bool = False,
) -> PropertyListResponse:
    with database.begin():
        database.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        definition, properties = content.schema(current.user_id, database_id)
        return PropertyListResponse(
            items=[
                PropertyResponse.model_validate(item)
                for item in properties
                if (item.trashed_at is not None) == trashed
            ],
            schema_version=definition.schema_version,
        )


@router.get("/{database_id}/properties/{property_id}", response_model=PropertyResponse)
def get_property(
    database_id: UUID,
    property_id: UUID,
    current: CurrentSession,
    database: Database,
    content: Content,
) -> PropertyResponse:
    with database.begin():
        database.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        _, properties = content.schema(current.user_id, database_id)
        return PropertyResponse.model_validate(content.definition(properties, property_id))


@router.patch(
    "/{database_id}/properties/{property_id}",
    response_model=PropertyResultResponse,
    dependencies=[Depends(require_csrf)],
)
def update_property(
    database_id: UUID,
    property_id: UUID,
    payload: PropertyPatch,
    current: CurrentSession,
    database: Database,
    content: Content,
) -> PropertyResultResponse:
    with database.begin():
        response = PropertyResultResponse.model_validate(
            content.update_property(
                current.user_id,
                database_id,
                property_id,
                payload.expected_version,
                payload.expected_schema_version,
                payload.model_dump(
                    exclude_unset=True, exclude={"expected_version", "expected_schema_version"}
                ),
            )
        )
    logger.info("workspace.database_property_updated", extra={"user_id": str(current.user_id)})
    return response


@router.post(
    "/{database_id}/properties/{property_id}/{action}",
    response_model=PropertyResultResponse,
    dependencies=[Depends(require_csrf)],
)
def property_lifecycle(
    database_id: UUID,
    property_id: UUID,
    action: Literal["trash", "restore"],
    payload: PropertyVersionRequest,
    current: CurrentSession,
    database: Database,
    content: Content,
) -> PropertyResultResponse:
    with database.begin():
        response = PropertyResultResponse.model_validate(
            content.property_lifecycle(
                current.user_id,
                database_id,
                property_id,
                payload.expected_version,
                payload.expected_schema_version,
                restore=action == "restore",
            )
        )
    logger.info("workspace.database_property_" + action, extra={"user_id": str(current.user_id)})
    return response


@router.post(
    "/{database_id}/records",
    status_code=201,
    response_model=RecordResultResponse,
    dependencies=[Depends(require_csrf)],
)
def create_record(
    database_id: UUID,
    payload: RecordCreate,
    current: CurrentSession,
    database: Database,
    content: Content,
) -> RecordResultResponse:
    with database.begin():
        response = RecordResultResponse.model_validate(
            content.create_record(current.user_id, database_id, **payload.model_dump())
        )
    logger.info("workspace.database_record_created", extra={"user_id": str(current.user_id)})
    return response


@router.get("/{database_id}/records", response_model=RecordListResponse)
def list_records(
    database_id: UUID,
    current: CurrentSession,
    database: Database,
    content: Content,
    trashed: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0, le=2**31 - 1)] = 0,
) -> RecordListResponse:
    with database.begin():
        database.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        return RecordListResponse(
            items=[
                RecordResultResponse.model_validate(item)
                for item in content.list_records(
                    current.user_id, database_id, trashed, limit, offset
                )
            ],
            limit=limit,
            offset=offset,
        )


@router.get("/{database_id}/records/{record_id}", response_model=RecordResultResponse)
def get_record(
    database_id: UUID,
    record_id: UUID,
    current: CurrentSession,
    database: Database,
    content: Content,
) -> RecordResultResponse:
    with database.begin():
        database.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        return RecordResultResponse.model_validate(
            content.get_record(current.user_id, database_id, record_id)
        )


@router.patch(
    "/{database_id}/records/{record_id}",
    response_model=RecordResultResponse,
    dependencies=[Depends(require_csrf)],
)
def update_record(
    database_id: UUID,
    record_id: UUID,
    payload: RecordPatch,
    current: CurrentSession,
    database: Database,
    content: Content,
) -> RecordResultResponse:
    with database.begin():
        response = RecordResultResponse.model_validate(
            content.update_record(
                current.user_id,
                database_id,
                record_id,
                payload.expected_version,
                payload.expected_schema_version,
                payload.values,
            )
        )
    logger.info("workspace.database_record_updated", extra={"user_id": str(current.user_id)})
    return response


@router.post(
    "/{database_id}/records/{record_id}/{action}",
    response_model=RecordResultResponse,
    dependencies=[Depends(require_csrf)],
)
def record_lifecycle(
    database_id: UUID,
    record_id: UUID,
    action: Literal["trash", "restore"],
    payload: VersionRequest,
    current: CurrentSession,
    database: Database,
    content: Content,
) -> RecordResultResponse:
    with database.begin():
        response = RecordResultResponse.model_validate(
            content.record_lifecycle(
                current.user_id,
                database_id,
                record_id,
                payload.expected_version,
                restore=action == "restore",
            )
        )
    logger.info("workspace.database_record_" + action, extra={"user_id": str(current.user_id)})
    return response


@page_router.get("/{page_id}/database-records", response_model=RecordListResponse)
def page_records(
    page_id: UUID,
    current: CurrentSession,
    database: Database,
    content: Content,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0, le=2**31 - 1)] = 0,
) -> RecordListResponse:
    with database.begin():
        database.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        return RecordListResponse(
            items=[
                RecordResultResponse.model_validate(item)
                for item in content.page_records(current.user_id, page_id, limit, offset)
            ],
            limit=limit,
            offset=offset,
        )
