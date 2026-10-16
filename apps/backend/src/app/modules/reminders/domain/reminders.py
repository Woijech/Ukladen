from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

ReminderSource = Literal["personal", "official"]
ReminderStatus = Literal["pending", "delivered", "cancelled"]


class InvalidReminderInput(ValueError):
    pass


class ReminderNotFound(Exception):
    pass


class ReminderConflict(Exception):
    pass


def trigger_time(starts_at: datetime, minutes_before: int, now: datetime) -> datetime:
    if (
        type(minutes_before) is not int
        or not 0 <= minutes_before <= 43200
        or starts_at.utcoffset() is None
        or now.utcoffset() is None
    ):
        raise InvalidReminderInput()
    try:
        due_at = starts_at.astimezone(UTC) - timedelta(minutes=minutes_before)
    except OverflowError, ValueError:
        raise InvalidReminderInput() from None
    if due_at <= now:
        raise InvalidReminderInput()
    return due_at


@dataclass(frozen=True, kw_only=True)
class Reminder:
    id: UUID
    user_id: UUID
    source: ReminderSource
    event_id: UUID
    minutes_before: int
    starts_at: datetime
    due_at: datetime
    status: ReminderStatus
    version: int
    created_at: datetime
    updated_at: datetime
