import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal, cast
from uuid import UUID

from app.modules.workspace.domain.databases import DatabaseProperty
from app.modules.workspace.domain.organization import InvalidWorkspaceInput
from app.modules.workspace.domain.properties import PropertyValue, property_id, property_value

FilterOperator = Literal[
    "eq", "neq", "contains", "gt", "gte", "lt", "lte", "is_empty", "is_not_empty"
]
FILTER_OPERATORS = ("eq", "neq", "contains", "gt", "gte", "lt", "lte", "is_empty", "is_not_empty")


@dataclass(frozen=True)
class PropertyFilter:
    property_id: UUID
    operator: FilterOperator
    value: PropertyValue = None


@dataclass(frozen=True)
class PropertySort:
    property_id: UUID
    direction: Literal["asc", "desc"] = "asc"


@dataclass(frozen=True)
class DatabaseQuery:
    columns: tuple[UUID, ...] | None = None
    filters: tuple[PropertyFilter, ...] = ()
    sorts: tuple[PropertySort, ...] = ()
    version: Literal[1] = 1


def parse_query(value: object) -> DatabaseQuery:
    if not isinstance(value, Mapping) or value.keys() - {"version", "columns", "filters", "sorts"}:
        raise InvalidWorkspaceInput()
    if type(value.get("version", 1)) is not int or value.get("version", 1) != 1:
        raise InvalidWorkspaceInput()
    raw_columns = value.get("columns")
    columns = None
    if raw_columns is not None:
        if not isinstance(raw_columns, (list, tuple)) or len(raw_columns) > 100:
            raise InvalidWorkspaceInput()
        columns = tuple(property_id(item) for item in raw_columns)
        if len(set(columns)) != len(columns):
            raise InvalidWorkspaceInput()
    raw_filters, raw_sorts = value.get("filters", ()), value.get("sorts", ())
    if (
        not isinstance(raw_filters, (list, tuple))
        or len(raw_filters) > 20
        or not isinstance(raw_sorts, (list, tuple))
        or len(raw_sorts) > 3
    ):
        raise InvalidWorkspaceInput()
    filters: list[PropertyFilter] = []
    for item in raw_filters:
        if not isinstance(item, Mapping) or item.keys() - {"property_id", "operator", "value"}:
            raise InvalidWorkspaceInput()
        operator = item.get("operator")
        if not isinstance(operator, str) or operator not in FILTER_OPERATORS:
            raise InvalidWorkspaceInput()
        filters.append(
            PropertyFilter(
                property_id(item.get("property_id")),
                cast(FilterOperator, operator),
                cast(PropertyValue, item.get("value")),
            )
        )
    sorts: list[PropertySort] = []
    for item in raw_sorts:
        if not isinstance(item, Mapping) or item.keys() - {"property_id", "direction"}:
            raise InvalidWorkspaceInput()
        direction = item.get("direction", "asc")
        if direction not in ("asc", "desc"):
            raise InvalidWorkspaceInput()
        sorts.append(PropertySort(property_id(item.get("property_id")), direction))
    if len({item.property_id for item in sorts}) != len(sorts):
        raise InvalidWorkspaceInput()
    return DatabaseQuery(columns, tuple(filters), tuple(sorts))


def query_value(query: DatabaseQuery) -> dict[str, object]:
    return {
        "version": query.version,
        "columns": [str(item) for item in query.columns] if query.columns is not None else None,
        "filters": [
            {"property_id": str(item.property_id), "operator": item.operator, "value": item.value}
            for item in query.filters
        ],
        "sorts": [
            {"property_id": str(item.property_id), "direction": item.direction}
            for item in query.sorts
        ],
    }


def validate_query(value: object, definitions: list[DatabaseProperty]) -> DatabaseQuery:
    query = parse_query(value)
    active = {item.id: item for item in definitions if item.trashed_at is None}
    references = {*query.columns} if query.columns is not None else set()
    references.update(item.property_id for item in (*query.filters, *query.sorts))
    if references - active.keys():
        raise InvalidWorkspaceInput()
    filters = []
    for item in query.filters:
        definition = active[item.property_id]
        if item.operator in ("is_empty", "is_not_empty"):
            if item.value is not None:
                raise InvalidWorkspaceInput()
            filters.append(item)
            continue
        if item.operator == "contains":
            if definition.kind == "text":
                normalized = property_value(definition, item.value)
                if normalized is None:
                    raise InvalidWorkspaceInput()
            elif definition.kind == "multi_select":
                selected = property_value(definition, [item.value])
                assert isinstance(selected, list)
                normalized = selected[0]
            else:
                raise InvalidWorkspaceInput()
        else:
            if definition.kind == "multi_select" or (
                item.operator not in ("eq", "neq") and definition.kind not in ("number", "date")
            ):
                raise InvalidWorkspaceInput()
            normalized = property_value(definition, item.value)
            if item.operator not in ("eq", "neq") and normalized is None:
                raise InvalidWorkspaceInput()
        filters.append(replace(item, value=normalized))
    if any(active[item.property_id].kind == "multi_select" for item in query.sorts):
        raise InvalidWorkspaceInput()
    query = replace(query, filters=tuple(filters))
    if (
        len(json.dumps(query_value(query), ensure_ascii=False, allow_nan=False).encode("utf-8"))
        > 65536
    ):
        raise InvalidWorkspaceInput()
    return query


@dataclass(frozen=True, kw_only=True)
class DatabaseView:
    id: UUID
    user_id: UUID
    database_id: UUID
    name: str
    color: str | None
    query: DatabaseQuery
    version: int
    created_at: datetime
    updated_at: datetime
    layout: Literal["table"] = "table"
