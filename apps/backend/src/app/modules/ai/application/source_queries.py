from datetime import date
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class ReadQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceScope(ReadQuery):
    page_ids: tuple[UUID, ...] = Field(default=(), max_length=20)
    material_ids: tuple[UUID, ...] = Field(default=(), max_length=20)
    database_ids: tuple[UUID, ...] = Field(default=(), max_length=20)
    calendar: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def bounded_selection(self) -> Self:
        if len(self.page_ids) + len(self.material_ids) + len(self.database_ids) > 20:
            raise ValueError("Select at most 20 explicit sources.")
        return self


class SearchRead(ReadQuery):
    query: str = Field(min_length=1, max_length=200)
    source: Literal["page", "material"] | None = None
    source_ids: tuple[UUID, ...] = Field(default=(), max_length=20)
    offset: int = Field(default=0, ge=0, le=1000, strict=True)
    limit: int = Field(default=5, ge=1, le=8, strict=True)


class PageRead(ReadQuery):
    page_id: UUID
    block_id: UUID | None = None
    offset: int = Field(default=0, ge=0, le=1048576, strict=True)
    limit: int = Field(default=2000, ge=1, le=2000, strict=True)


class MaterialRead(ReadQuery):
    material_id: UUID
    offset: int = Field(default=0, ge=0, le=2097152, strict=True)
    limit: int = Field(default=2000, ge=1, le=2000, strict=True)


class CalendarRead(ReadQuery):
    date_from: date
    date_to: date
    include_hidden: bool = Field(default=False, strict=True)
    database_view_ids: tuple[UUID, ...] | None = Field(default=None, max_length=20)
    offset: int = Field(default=0, ge=0, le=10000, strict=True)
    limit: int = Field(default=5, ge=1, le=20, strict=True)


class DatabaseList(ReadQuery):
    offset: int = Field(default=0, ge=0, le=10000, strict=True)
    limit: int = Field(default=5, ge=1, le=20, strict=True)


class DatabaseRead(ReadQuery):
    database_id: UUID
    property_id: UUID | None = None
    offset: int = Field(default=0, ge=0, le=10000, strict=True)
    limit: int = Field(default=5, ge=1, le=10, strict=True)


class PropertyFilter(ReadQuery):
    property_id: UUID
    operator: Literal["eq", "neq", "contains", "gt", "gte", "lt", "lte", "is_empty", "is_not_empty"]
    value: JsonValue = None


class PropertySort(ReadQuery):
    property_id: UUID
    direction: Literal["asc", "desc"] = "asc"


class DatabaseReadQuery(ReadQuery):
    database_id: UUID
    view_id: UUID | None = None
    filters: tuple[PropertyFilter, ...] = Field(default=(), max_length=20)
    sorts: tuple[PropertySort, ...] = Field(default=(), max_length=3)
    columns: tuple[UUID, ...] | None = Field(default=None, max_length=100)
    offset: int = Field(default=0, ge=0, le=10000, strict=True)
    limit: int = Field(default=5, ge=1, le=20, strict=True)


class RecordRead(ReadQuery):
    """Current read-only source inspection; not an additional advertised agent tool."""

    database_id: UUID
    record_id: UUID
    offset: int = Field(default=0, ge=0, le=100, strict=True)
    limit: int = Field(default=5, ge=1, le=5, strict=True)


SourceQuery = (
    SearchRead
    | PageRead
    | MaterialRead
    | CalendarRead
    | DatabaseList
    | DatabaseRead
    | DatabaseReadQuery
    | RecordRead
)

# Tool names are stable capabilities; retrieval implementation is independent of the model.
READ_QUERIES: dict[str, type[ReadQuery]] = {
    "search_workspace": SearchRead,
    "read_page": PageRead,
    "read_material_excerpt": MaterialRead,
    "get_calendar_events": CalendarRead,
    "list_databases": DatabaseList,
    "read_database": DatabaseRead,
    "query_database": DatabaseReadQuery,
}


def restrict_source_query(query: ReadQuery, scope: SourceScope | None) -> ReadQuery | None:
    if scope is None:
        return query
    if isinstance(query, SearchRead):
        if query.source is None:
            if scope.page_ids and scope.material_ids:
                raise ValueError("Search each selected source type separately.")
            query = query.model_copy(update={"source": "page" if scope.page_ids else "material"})
        allowed = (
            scope.page_ids
            if query.source == "page"
            else scope.material_ids
            if query.source == "material"
            else (*scope.page_ids, *scope.material_ids)
        )
        if query.source_ids:
            allowed = tuple(item for item in query.source_ids if item in allowed)
        return query.model_copy(update={"source_ids": allowed}) if allowed else None
    if isinstance(query, PageRead):
        return query if query.page_id in scope.page_ids else None
    if isinstance(query, MaterialRead):
        return query if query.material_id in scope.material_ids else None
    if isinstance(query, (DatabaseRead, DatabaseReadQuery)):
        return query if query.database_id in scope.database_ids else None
    if isinstance(query, CalendarRead):
        return query if scope.calendar else None
    if isinstance(query, DatabaseList):
        return None
    return None
