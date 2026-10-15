from dataclasses import dataclass
from datetime import date
from typing import Literal, Protocol
from uuid import UUID


@dataclass(frozen=True, kw_only=True)
class RecordDateProjection:
    id: str
    database_id: UUID
    record_id: UUID
    page_id: UUID
    property_id: UUID
    title: str
    date: dict[str, str | None]
    record_version: int
    schema_version: int
    source: Literal["record_date"] = "record_date"
    blocks_time: Literal[False] = False


class RecordCalendarQuery(Protocol):
    def entries(
        self, user_id: UUID, view_id: UUID, date_from: date, date_to: date, timezone: str
    ) -> list[RecordDateProjection]: ...
