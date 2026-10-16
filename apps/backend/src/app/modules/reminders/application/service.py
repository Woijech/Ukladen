from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.modules.calendar.application.service import CalendarEventReference, CalendarService
from app.modules.reminders.application.ports import ReminderRepository
from app.modules.reminders.domain.reminders import (
    InvalidReminderInput,
    Reminder,
    ReminderConflict,
    ReminderNotFound,
    ReminderSource,
    trigger_time,
)
from app.modules.users.application.ports import UserAuthentication
from app.modules.users.domain.profile import ProfileUnavailable


class ReminderService:
    """One-shot event reminders; callers own transactions and lock owners before delivery."""

    def __init__(
        self,
        repository: ReminderRepository,
        users: UserAuthentication,
        calendar: CalendarService,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.repository, self.users, self.calendar, self.now = repository, users, calendar, now

    def require_user(self, user_id: UUID, *, write: bool = False) -> None:
        active = self.users.lock_active(user_id) if write else self.users.is_active(user_id)
        if not active:
            raise ProfileUnavailable()

    def target(
        self, user_id: UUID, source: ReminderSource, event_id: UUID
    ) -> CalendarEventReference:
        if source not in ("personal", "official"):
            raise InvalidReminderInput()
        self.calendar.require_link_target(user_id, source, event_id)
        event = self.calendar.linked_event_references(user_id, ((source, event_id),)).get(
            (source, event_id)
        )
        if event is None or event.source_status != "active" or event.skipped:
            raise ReminderConflict()
        return event

    def get(self, user_id: UUID, reminder_id: UUID) -> Reminder:
        self.require_user(user_id)
        reminder = self.repository.get(user_id, reminder_id)
        if reminder is None:
            raise ReminderNotFound()
        return reminder

    def list(self, user_id: UUID, limit: int = 100, offset: int = 0) -> list[Reminder]:
        self.require_user(user_id)
        if (
            type(limit) is not int
            or type(offset) is not int
            or not (1 <= limit <= 200 and 0 <= offset <= 2**31 - 1)
        ):
            raise InvalidReminderInput()
        return self.repository.list(user_id, limit, offset)

    def create(
        self, user_id: UUID, source: ReminderSource, event_id: UUID, minutes_before: int
    ) -> Reminder:
        self.require_user(user_id, write=True)
        event, now = self.target(user_id, source, event_id), self.now()
        reminder = Reminder(
            id=uuid4(),
            user_id=user_id,
            source=source,
            event_id=event_id,
            minutes_before=minutes_before,
            starts_at=event.starts_at,
            due_at=trigger_time(event.starts_at, minutes_before, now),
            status="pending",
            version=1,
            created_at=now,
            updated_at=now,
        )
        self.repository.create(reminder)
        return reminder

    @staticmethod
    def require_version(reminder: Reminder, expected_version: int) -> None:
        if type(expected_version) is not int or expected_version < 1:
            raise InvalidReminderInput()
        if reminder.version != expected_version:
            raise ReminderConflict()

    def update(
        self, user_id: UUID, reminder_id: UUID, minutes_before: int, expected_version: int
    ) -> Reminder:
        self.require_user(user_id, write=True)
        reminder = self.get(user_id, reminder_id)
        self.require_version(reminder, expected_version)
        if reminder.status != "pending":
            raise ReminderConflict()
        event, now = self.target(user_id, reminder.source, reminder.event_id), self.now()
        updated = replace(
            reminder,
            minutes_before=minutes_before,
            starts_at=event.starts_at,
            due_at=trigger_time(event.starts_at, minutes_before, now),
            version=reminder.version + 1,
            updated_at=now,
        )
        self.repository.save(updated, expected_version)
        return updated

    def cancel(self, user_id: UUID, reminder_id: UUID, expected_version: int) -> Reminder:
        self.require_user(user_id, write=True)
        reminder = self.get(user_id, reminder_id)
        self.require_version(reminder, expected_version)
        if reminder.status == "delivered":
            raise ReminderConflict()
        if reminder.status == "cancelled":
            return reminder
        updated = replace(
            reminder, status="cancelled", version=reminder.version + 1, updated_at=self.now()
        )
        self.repository.save(updated, expected_version)
        return updated

    def delete(self, user_id: UUID, reminder_id: UUID, expected_version: int) -> None:
        self.require_user(user_id, write=True)
        self.require_version(self.get(user_id, reminder_id), expected_version)
        self.repository.delete(user_id, reminder_id)
