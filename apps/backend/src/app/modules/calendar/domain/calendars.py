from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, kw_only=True)
class PersonalCalendar:
    id: UUID
    user_id: UUID
    name: str
    color: str
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class CalendarVisibility:
    version: int = 0
    default_visible: bool = True
    hidden_calendar_ids: tuple[UUID, ...] = ()
    hidden_lesson_types: tuple[str, ...] = ()
