from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.modules.calendar.application.ports import PersonalCalendarEventRepository
from app.modules.calendar.domain.errors import EventNotFound, InvalidEventInput
from app.modules.calendar.domain.events import (
    PersonalCalendarEvent,
    apply_event_changes,
    new_personal_event,
)
from app.modules.users.application.ports import UserAuthentication
from app.modules.users.domain.profile import ProfileUnavailable

MAX_PERIOD = timedelta(days=366)


class PersonalEventService:
    """Owner-scoped event use cases inside caller-owned transactions.

    Reads and writes never commit: the HTTP layer owns the transaction and only
    exposes results after it completes successfully.
    """

    def __init__(
        self, repository: PersonalCalendarEventRepository, users: UserAuthentication
    ) -> None:
        self.repository = repository
        self.users = users

    def list(
        self, user_id: UUID, starts_at: datetime, ends_at: datetime
    ) -> list[PersonalCalendarEvent]:
        self._require_period(starts_at, ends_at)
        return self.repository.list_for_period(user_id, starts_at, ends_at)

    def get(self, user_id: UUID, event_id: UUID) -> PersonalCalendarEvent:
        self._require_active(user_id)
        event = self.repository.get(user_id, event_id)
        if event is None:
            raise EventNotFound("Event not found.")
        return event

    def create(self, user_id: UUID, values: Mapping[str, object]) -> PersonalCalendarEvent:
        self._require_active(user_id, write=True)
        event = new_personal_event(user_id, values, now=datetime.now(UTC))
        return self.repository.create(user_id, event)

    def update(
        self, user_id: UUID, event_id: UUID, changes: Mapping[str, object]
    ) -> PersonalCalendarEvent:
        self._require_active(user_id, write=True)
        current = self.repository.get(user_id, event_id)
        if current is None:
            raise EventNotFound("Event not found.")
        event = apply_event_changes(current, changes)
        updated = self.repository.update(user_id, event)
        if updated is None:
            raise EventNotFound("Event not found.")
        return updated

    def delete(self, user_id: UUID, event_id: UUID) -> None:
        self._require_active(user_id, write=True)
        if not self.repository.delete(user_id, event_id):
            raise EventNotFound("Event not found.")

    def _require_active(self, user_id: UUID, *, write: bool = False) -> None:
        if not self.users.is_active(user_id):
            raise ProfileUnavailable()
        if write and not self.users.lock_active(user_id):
            raise ProfileUnavailable()

    @staticmethod
    def _require_period(starts_at: datetime, ends_at: datetime) -> None:
        if starts_at.utcoffset() is None or ends_at.utcoffset() is None:
            raise InvalidEventInput("Period timestamps must be timezone-aware.")
        start, end = starts_at.astimezone(UTC), ends_at.astimezone(UTC)
        if start >= end:
            raise InvalidEventInput("Period end must be after its start.")
        if end - start > MAX_PERIOD:
            raise InvalidEventInput("Period is too long.")
