from dataclasses import replace
from uuid import UUID, uuid4

from app.modules.calendar.domain.events import CalendarConflict, CalendarEventNotFound
from app.modules.notifications.application.service import NotificationService
from app.modules.notifications.domain.notifications import Notification
from app.modules.reminders.application.service import ReminderService
from app.modules.reminders.domain.reminders import ReminderConflict


class ReminderDispatchUnavailable(Exception):
    pass


class ReminderDeliveryService:
    """Deliver one current reminder atomically with its inbox record; callers commit."""

    def __init__(self, reminders: ReminderService, notifications: NotificationService) -> None:
        self.reminders, self.notifications = reminders, notifications

    def deliver(self, user_id: UUID, reminder_id: UUID) -> None:
        # Match calendar/reminder mutation lock order: owner first, then reminder writes.
        active = self.reminders.users.lock_active(user_id)
        reminder = self.reminders.repository.get(user_id, reminder_id)
        now = self.reminders.now()
        if reminder is None or reminder.status != "pending" or reminder.due_at > now:
            return
        event = None
        if active:
            try:
                event = self.reminders.target(user_id, reminder.source, reminder.event_id)
            except CalendarEventNotFound, CalendarConflict, ReminderConflict:
                pass
        valid = event is not None and event.starts_at == reminder.starts_at and event.ends_at > now
        if valid:
            assert event is not None
            self.notifications.publish(
                Notification(
                    id=uuid4(),
                    user_id=user_id,
                    reminder_id=reminder.id,
                    source=reminder.source,
                    event_id=reminder.event_id,
                    title=event.title[:500],
                    starts_at=event.starts_at,
                    created_at=now,
                )
            )
        self.reminders.repository.save(
            replace(
                reminder,
                status="delivered" if valid else "cancelled",
                version=reminder.version + 1,
                updated_at=now,
            ),
            reminder.version,
        )
