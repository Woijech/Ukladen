from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.modules.academics.presentation.routes import no_store
from app.modules.auth.presentation.dependencies import (
    CurrentSession,
    Database,
    get_current_session,
    require_csrf,
)
from app.modules.materials.presentation.routes import Materials
from app.modules.materials.presentation.schemas import MaterialListResponse, MaterialResponse
from app.modules.notes.presentation.routes import Notes
from app.modules.notes.presentation.schemas import PageSummary
from app.modules.relations.application.materials import MaterialRelationService
from app.modules.relations.infrastructure.materials import SqlAlchemyPageMaterialLinks

router = APIRouter(
    prefix="/api/v1/relations",
    tags=["relations"],
    dependencies=[Depends(get_current_session), Depends(no_store)],
)


class LinkedMaterialPagesResponse(BaseModel):
    items: list[PageSummary]
    limit: int
    offset: int


def get_material_relations(
    database: Database, notes: Notes, materials: Materials
) -> MaterialRelationService:
    return MaterialRelationService(SqlAlchemyPageMaterialLinks(database), notes, materials)


MaterialRelations = Annotated[MaterialRelationService, Depends(get_material_relations)]


@router.put(
    "/pages/{page_id}/materials/{material_id}",
    response_model=MaterialResponse,
    dependencies=[Depends(require_csrf)],
)
def link_material(
    page_id: UUID,
    material_id: UUID,
    current: CurrentSession,
    database: Database,
    relations: MaterialRelations,
) -> MaterialResponse:
    with database.begin():
        result = MaterialResponse.model_validate(
            relations.link(current.user_id, page_id, material_id)
        )
    return result


@router.delete(
    "/pages/{page_id}/materials/{material_id}",
    status_code=204,
    dependencies=[Depends(require_csrf)],
)
def unlink_material(
    page_id: UUID,
    material_id: UUID,
    current: CurrentSession,
    database: Database,
    relations: MaterialRelations,
) -> None:
    with database.begin():
        relations.unlink(current.user_id, page_id, material_id)


@router.get("/pages/{page_id}/materials", response_model=MaterialListResponse)
def page_materials(
    page_id: UUID,
    current: CurrentSession,
    database: Database,
    relations: MaterialRelations,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0, le=2**31 - 1)] = 0,
) -> MaterialListResponse:
    with database.begin():
        return MaterialListResponse(
            items=[
                MaterialResponse.model_validate(item)
                for item in relations.for_page(current.user_id, page_id, limit, offset)
            ],
            limit=limit,
            offset=offset,
        )


@router.get("/materials/{material_id}/pages", response_model=LinkedMaterialPagesResponse)
def material_pages(
    material_id: UUID,
    current: CurrentSession,
    database: Database,
    relations: MaterialRelations,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0, le=2**31 - 1)] = 0,
) -> LinkedMaterialPagesResponse:
    with database.begin():
        return LinkedMaterialPagesResponse(
            items=[
                PageSummary.model_validate(item)
                for item in relations.for_material(current.user_id, material_id, limit, offset)
            ],
            limit=limit,
            offset=offset,
        )
