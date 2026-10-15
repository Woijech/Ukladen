import logging
from typing import Annotated, Literal, Self
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.modules.academics.presentation.routes import no_store
from app.modules.auth.presentation.dependencies import (
    CurrentSession,
    Database,
    get_current_session,
    require_csrf,
)
from app.modules.workspace.application.database_views import DatabaseViewService
from app.modules.workspace.domain.database_views import FilterOperator
from app.modules.workspace.domain.organization import InvalidWorkspaceInput
from app.modules.workspace.infrastructure.database_views import SqlAlchemyDatabaseViews
from app.modules.workspace.presentation.database_content import Content
from app.modules.workspace.presentation.database_schemas import (
    PropertyResponse,
    RecordResultResponse,
    SchemaVersionRequest,
)
from app.modules.workspace.presentation.schemas import OrganizationCreate, OrganizationPatch

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/v1/workspace/databases/{database_id}/views",
    tags=["workspace database views"],
    dependencies=[Depends(no_store), Depends(get_current_session)],
)


class FilterSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    property_id: UUID
    operator: FilterOperator
    value: object = None


class SortSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    property_id: UUID
    direction: Literal["asc", "desc"] = "asc"


class QuerySchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    version: int = Field(default=1, ge=1, le=1, strict=True)
    columns: list[UUID] | None = Field(default=None, max_length=100)
    filters: list[FilterSchema] = Field(default_factory=list, max_length=20)
    sorts: list[SortSchema] = Field(default_factory=list, max_length=3)


class ViewCreate(OrganizationCreate, SchemaVersionRequest):
    query: QuerySchema = Field(default_factory=QuerySchema)


class ViewPatch(OrganizationPatch):
    expected_schema_version: int = Field(ge=1, le=2**31 - 2, strict=True)
    query: QuerySchema | None = None

    @model_validator(mode="after")
    def validate_view_changes(self) -> Self:
        changes = self.model_dump(
            exclude_unset=True, exclude={"expected_version", "expected_schema_version"}
        )
        if not changes or ("query" in changes and changes["query"] is None):
            raise InvalidWorkspaceInput()
        return self


class ViewResponse(OrganizationCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    database_id: UUID
    query: QuerySchema
    layout: Literal["table"]
    version: int
    created_at: AwareDatetime
    updated_at: AwareDatetime


class ViewListResponse(BaseModel):
    items: list[ViewResponse]
    limit: int
    offset: int


class TableResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    view: ViewResponse
    properties: list[PropertyResponse]
    items: list[RecordResultResponse]
    schema_version: int
    total: int
    limit: int
    offset: int


def get_views(database: Database, content: Content) -> DatabaseViewService:
    return DatabaseViewService(SqlAlchemyDatabaseViews(database), content)


Views = Annotated[DatabaseViewService, Depends(get_views)]


@router.post("", status_code=201, response_model=ViewResponse, dependencies=[Depends(require_csrf)])
def create_view(
    database_id: UUID,
    payload: ViewCreate,
    current: CurrentSession,
    database: Database,
    views: Views,
) -> ViewResponse:
    with database.begin():
        response = ViewResponse.model_validate(
            views.create(current.user_id, database_id, **payload.model_dump())
        )
    logger.info("workspace.database_view_created", extra={"user_id": str(current.user_id)})
    return response


@router.get("", response_model=ViewListResponse)
def list_views(
    database_id: UUID,
    current: CurrentSession,
    database: Database,
    views: Views,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0, le=2**31 - 1)] = 0,
) -> ViewListResponse:
    with database.begin():
        return ViewListResponse(
            items=[
                ViewResponse.model_validate(item)
                for item in views.list(current.user_id, database_id, limit, offset)
            ],
            limit=limit,
            offset=offset,
        )


@router.get("/{view_id}", response_model=ViewResponse)
def get_view(
    database_id: UUID, view_id: UUID, current: CurrentSession, database: Database, views: Views
) -> ViewResponse:
    with database.begin():
        return ViewResponse.model_validate(views.get(current.user_id, database_id, view_id))


@router.patch("/{view_id}", response_model=ViewResponse, dependencies=[Depends(require_csrf)])
def update_view(
    database_id: UUID,
    view_id: UUID,
    payload: ViewPatch,
    current: CurrentSession,
    database: Database,
    views: Views,
) -> ViewResponse:
    with database.begin():
        response = ViewResponse.model_validate(
            views.update(
                current.user_id,
                database_id,
                view_id,
                payload.expected_version,
                payload.expected_schema_version,
                payload.model_dump(
                    exclude_unset=True, exclude={"expected_version", "expected_schema_version"}
                ),
            )
        )
    logger.info("workspace.database_view_updated", extra={"user_id": str(current.user_id)})
    return response


@router.delete("/{view_id}", status_code=204, dependencies=[Depends(require_csrf)])
def delete_view(
    database_id: UUID,
    view_id: UUID,
    current: CurrentSession,
    database: Database,
    views: Views,
    expected_version: Annotated[int, Query(ge=1, le=2**31 - 2)],
) -> None:
    with database.begin():
        views.delete(current.user_id, database_id, view_id, expected_version)
    logger.info("workspace.database_view_deleted", extra={"user_id": str(current.user_id)})


@router.get("/{view_id}/records", response_model=TableResponse)
def table_records(
    database_id: UUID,
    view_id: UUID,
    current: CurrentSession,
    database: Database,
    views: Views,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0, le=2**31 - 1)] = 0,
) -> TableResponse:
    with database.begin():
        database.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        response = TableResponse.model_validate(
            views.table(current.user_id, database_id, view_id, limit, offset)
        )
    logger.info(
        "workspace.database_view_queried",
        extra={"user_id": str(current.user_id), "record_count": len(response.items)},
    )
    return response
