import logging
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from app.core.logging import log_failure
from app.modules.academics.application.ports import AcademicProvider
from app.modules.academics.application.profile import AcademicService
from app.modules.academics.infrastructure.repository import SqlAlchemyAcademicProfileRepository
from app.modules.calendar.application.service import CalendarService
from app.modules.calendar.infrastructure.repository import SqlAlchemyCalendarRepository
from app.modules.notifications.application.service import NotificationService
from app.modules.notifications.infrastructure.repository import SqlAlchemyNotificationRepository
from app.modules.reminders.application.delivery import (
    ReminderDeliveryService,
    ReminderDispatchUnavailable,
)
from app.modules.reminders.application.service import ReminderService
from app.modules.reminders.infrastructure.repository import SqlAlchemyReminderRepository
from app.modules.schedule.application.queries import ScheduleQueryService
from app.modules.schedule.infrastructure.storage import SqlAlchemyScheduleStore
from app.modules.users.infrastructure.repository import (
    SqlAlchemyProfileRepository,
    SqlAlchemyUserAuthentication,
)

logger = logging.getLogger(__name__)


def delivery_service(
    database: Session,
    sessions: sessionmaker[Session],
    provider: AcademicProvider,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> ReminderDeliveryService:
    users = SqlAlchemyUserAuthentication(database)
    calendar = CalendarService(
        SqlAlchemyCalendarRepository(database),
        SqlAlchemyProfileRepository(database),
        AcademicService(SqlAlchemyAcademicProfileRepository(database), users, provider),
        ScheduleQueryService(SqlAlchemyScheduleStore(sessions, read_session=database)),
    )
    return ReminderDeliveryService(
        ReminderService(SqlAlchemyReminderRepository(database), users, calendar, now=now),
        NotificationService(SqlAlchemyNotificationRepository(database), users, now=now),
    )


def dispatch_due(
    sessions: sessionmaker[Session],
    provider: AcademicProvider,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> None:
    with sessions.begin() as database:
        due = SqlAlchemyReminderRepository(database).due(now(), 200)
    failed = False
    for user_id, reminder_id in due:
        try:
            with sessions.begin() as database:
                delivery_service(database, sessions, provider, now=now).deliver(
                    user_id, reminder_id
                )
        except Exception as error:
            # One failing reminder must not stop unrelated owners in the same batch.
            failed = True
            log_failure(logger, "reminders.delivery_failed", error)
    if failed:
        raise ReminderDispatchUnavailable("Reminder dispatch is unavailable.")
