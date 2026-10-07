from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.calendar.domain.events import PersonalCalendarEvent


class PersonalCalendarEventRepository(Protocol):
    """Persist owner-scoped events in the caller's transaction; never commit."""

    def create(self, user_id: UUID, event: PersonalCalendarEvent) -> PersonalCalendarEvent:
        """Insert an event whose owner matches user_id; fail on a duplicate ID."""
        ...

    def get(self, user_id: UUID, event_id: UUID) -> PersonalCalendarEvent | None: ...

    def list_for_period(
        self, user_id: UUID, starts_at: datetime, ends_at: datetime
    ) -> list[PersonalCalendarEvent]:
        """Return events overlapping [starts_at, ends_at), ordered by start and ID."""
        ...

    def update(self, user_id: UUID, event: PersonalCalendarEvent) -> PersonalCalendarEvent | None:
        """Replace mutable fields of an owned event; preserve ownership and creation time."""
        ...

    def delete(self, user_id: UUID, event_id: UUID) -> bool:
        """Delete an owned event; return false for both missing and foreign events."""
        ...
