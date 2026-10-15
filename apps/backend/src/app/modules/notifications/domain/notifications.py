from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID


class NotificationNotFound(Exception):
    pass


@dataclass(frozen=True, kw_only=True)
class Notification:
    id: UUID
    user_id: UUID
    reminder_id: UUID
    source: Literal["personal", "official"]
    event_id: UUID
    title: str
    starts_at: datetime
    created_at: datetime
    read_at: datetime | None = None
