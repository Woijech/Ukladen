from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, TypedDict
from uuid import UUID

from app.modules.workspace.domain.organization import InvalidWorkspaceInput, organization_values

EventSource = Literal["official", "personal"]
CalendarLayout = Literal["day", "week", "month"]
SortOrder = Literal["asc", "desc"]


@dataclass(frozen=True)
class CalendarViewSource:
    source: EventSource
    collection_ids: tuple[UUID, ...] = ()
    tag_ids: tuple[UUID, ...] = ()


def source_filters(value: object) -> tuple[CalendarViewSource, ...]:
    if not isinstance(value, (list, tuple)) or not 1 <= len(value) <= 2:
        raise InvalidWorkspaceInput()
    result: list[CalendarViewSource] = []
    for item in value:
        if not isinstance(item, Mapping) or item.keys() - {"source", "collection_ids", "tag_ids"}:
            raise InvalidWorkspaceInput()
        source = item.get("source")
        if source not in ("official", "personal") or any(row.source == source for row in result):
            raise InvalidWorkspaceInput()
        identifiers: list[tuple[UUID, ...]] = []
        for field in ("collection_ids", "tag_ids"):
            raw = item.get(field, ())
            if not isinstance(raw, (list, tuple)) or len(raw) > 20:
                raise InvalidWorkspaceInput()
            try:
                ids = tuple(
                    identifier if isinstance(identifier, UUID) else UUID(identifier)
                    for identifier in raw
                    if isinstance(identifier, (UUID, str))
                )
            except ValueError:
                raise InvalidWorkspaceInput() from None
            if len(ids) != len(raw) or len(set(ids)) != len(ids):
                raise InvalidWorkspaceInput()
            identifiers.append(ids)
        result.append(CalendarViewSource(source, *identifiers))
    return tuple(result)


class CalendarViewValues(TypedDict):
    name: str
    color: str | None
    sources: tuple[CalendarViewSource, ...]
    layout: CalendarLayout
    sort_order: SortOrder
    include_hidden: bool


def view_values(values: Mapping[str, object]) -> CalendarViewValues:
    if values.keys() - {"name", "color", "sources", "layout", "sort_order", "include_hidden"}:
        raise InvalidWorkspaceInput()
    name, color = organization_values(values.get("name"), values.get("color"))
    layout, sort_order = values.get("layout", "week"), values.get("sort_order", "asc")
    include_hidden = values.get("include_hidden", False)
    if layout not in ("day", "week", "month") or sort_order not in ("asc", "desc"):
        raise InvalidWorkspaceInput()
    if type(include_hidden) is not bool:
        raise InvalidWorkspaceInput()
    return {
        "name": name,
        "color": color,
        "sources": source_filters(
            values.get("sources", [{"source": "official"}, {"source": "personal"}])
        ),
        "layout": layout,
        "sort_order": sort_order,
        "include_hidden": include_hidden,
    }


@dataclass(frozen=True, kw_only=True)
class CalendarView:
    id: UUID
    user_id: UUID
    name: str
    color: str | None
    sources: tuple[CalendarViewSource, ...]
    layout: CalendarLayout
    sort_order: SortOrder
    include_hidden: bool
    version: int
    created_at: datetime
    updated_at: datetime
