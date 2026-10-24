from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class ReadQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceScope(ReadQuery):
    page_ids: tuple[UUID, ...] = Field(default=(), max_length=20)
    material_ids: tuple[UUID, ...] = Field(default=(), max_length=20)
    database_ids: tuple[UUID, ...] = Field(default=(), max_length=20)
    calendar: bool = Field(default=False, strict=True)


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
    limit: int = Field(default=10, ge=1, le=20, strict=True)


class DatabaseList(ReadQuery):
    offset: int = Field(default=0, ge=0, le=10000, strict=True)
    limit: int = Field(default=10, ge=1, le=20, strict=True)


class DatabaseRead(ReadQuery):
    database_id: UUID


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


SourceQuery = (
    SearchRead
    | PageRead
    | MaterialRead
    | CalendarRead
    | DatabaseList
    | DatabaseRead
    | DatabaseReadQuery
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
