from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from app.modules.academics.presentation.routes import no_store
from app.modules.auth.presentation.dependencies import CurrentSession, Database, get_current_session
from app.modules.materials.infrastructure.search import SqlAlchemyMaterialSearch
from app.modules.notes.infrastructure.search import SqlAlchemyPageSearch
from app.modules.search.application.service import SearchService
from app.modules.search.domain.search import InvalidSearchInput, SearchQuery
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication


class SearchHitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    source: Literal["page", "material"]
    id: UUID
    title: str
    snippet: str
    score: float
    version: int
    kind: Literal["file", "link"] | None


class SearchResponse(BaseModel):
    items: list[SearchHitResponse]
    limit: int
    offset: int


router = APIRouter(
    prefix="/api/v1/search",
    tags=["search"],
    dependencies=[Depends(get_current_session), Depends(no_store)],
)


def get_search(database: Database) -> SearchService:
    return SearchService(
        SqlAlchemyUserAuthentication(database),
        SqlAlchemyPageSearch(database),
        SqlAlchemyMaterialSearch(database),
    )


Search = Annotated[SearchService, Depends(get_search)]


@router.get("", response_model=SearchResponse)
def search(
    current: CurrentSession,
    database: Database,
    service: Search,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    source: Literal["page", "material"] | None = None,
    kind: Literal["file", "link"] | None = None,
    extension: Literal["pdf", "docx", "pptx", "txt", "md"] | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0, le=1000)] = 0,
) -> SearchResponse:
    with database.begin():
        database.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        result = service.search(
            current.user_id, SearchQuery(q, source, kind, extension, limit, offset)
        )
        return SearchResponse(
            items=[SearchHitResponse.model_validate(item) for item in result],
            limit=limit,
            offset=offset,
        )


def install_search(application: FastAPI) -> None:
    def invalid_search(request: Request, error: Exception) -> JSONResponse:
        return JSONResponse(
            {"detail": "Invalid search query or filters."},
            status_code=422,
            headers={"Cache-Control": "no-store"},
        )

    application.add_exception_handler(InvalidSearchInput, invalid_search)
    application.include_router(router)
