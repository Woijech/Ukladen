from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID


class NotificationNotFound(Exception):
    pass


class InvalidNotificationInput(ValueError):
    pass


@dataclass(frozen=True, kw_only=True)
class Notification:
    id: UUID
    user_id: UUID
    reminder_id: UUID | None = None
    source: Literal["personal", "official"] | None = None
    event_id: UUID | None = None
    title: str
    starts_at: datetime | None = None
    created_at: datetime
    read_at: datetime | None = None
    kind: Literal["reminder", "ai_review"] = "reminder"
    review_id: UUID | None = None

    def __post_init__(self):
        event = (self.reminder_id, self.source, self.event_id, self.starts_at)
        if not (
            (
                self.kind == "reminder"
                and all(value is not None for value in event)
                and self.review_id is None
            )
            or (
                self.kind == "ai_review"
                and all(value is None for value in event)
                and self.review_id is not None
            )
        ):
            raise InvalidNotificationInput()
