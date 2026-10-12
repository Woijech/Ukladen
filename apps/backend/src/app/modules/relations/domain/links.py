from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID


class RelationNotFound(Exception):
    pass


class InvalidRelationInput(ValueError):
    pass


@dataclass(frozen=True)
class CalendarPageLink:
    id: UUID
    user_id: UUID
    page_id: UUID
    source: Literal["personal", "official"]
    event_id: UUID
    created_at: datetime
