from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import Connection, delete, insert, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_auth_persistence import database_connection as database_connection
from test_auth_persistence import migration_config

from alembic import command
from app.modules.calendar.infrastructure.orm import PersonalCalendarEventModel
from app.modules.notifications.domain.notifications import Notification
from app.modules.notifications.infrastructure.orm import NotificationModel
from app.modules.notifications.infrastructure.repository import SqlAlchemyNotificationRepository
from app.modules.reminders.domain.reminders import Reminder
from app.modules.reminders.infrastructure.orm import ReminderModel
from app.modules.reminders.infrastructure.repository import SqlAlchemyReminderRepository
from app.modules.users.infrastructure.orm import UserModel


def test_constraints_deduplication_lifecycle_and_migration(database_connection: Connection) -> None:
    config = migration_config(database_connection)
    command.check(config)
    now = datetime.now(UTC)
    owner, other, event_id = uuid4(), uuid4(), uuid4()
    reminder = Reminder(
        id=uuid4(),
        user_id=owner,
        source="personal",
        event_id=event_id,
        minutes_before=15,
        starts_at=now + timedelta(hours=1),
        due_at=now + timedelta(minutes=45),
        status="pending",
        version=1,
        created_at=now,
        updated_at=now,
    )
    with Session(database_connection, join_transaction_mode="create_savepoint") as session:
        session.add_all(
            [
                UserModel(id=owner, email="reminder@example.com"),
                UserModel(id=other, email="other@example.com"),
            ]
        )
        session.flush()
        session.add(
            PersonalCalendarEventModel(
                id=event_id,
                user_id=owner,
                title="Study",
                starts_at=reminder.starts_at,
                ends_at=reminder.starts_at + timedelta(hours=1),
            )
        )
        session.flush()
        repository = SqlAlchemyReminderRepository(session)
        repository.create(reminder)
        assert repository.get(owner, reminder.id) == reminder
        assert repository.get(other, reminder.id) is None
        assert repository.list(other, 100, 0) == []
        assert repository.due(now, 100) == []
        assert repository.due(reminder.due_at, 100) == [(owner, reminder.id)]
        for changes in (
            {"user_id": other},
            {"minutes_before": -1},
            {"minutes_before": 43201},
            {"version": 0},
            {"status": "unknown"},
            {"due_at": now},
            {"personal_event_id": None},
            {"official_event_id": uuid4()},
        ):
            with pytest.raises(IntegrityError), session.begin_nested():
                session.execute(
                    insert(ReminderModel).values(
                        **(
                            {
                                "id": uuid4(),
                                "user_id": owner,
                                "personal_event_id": event_id,
                                "minutes_before": 15,
                                "starts_at": reminder.starts_at,
                                "due_at": reminder.due_at,
                                "status": "pending",
                                "version": 1,
                                "created_at": now,
                                "updated_at": now,
                            }
                            | changes
                        )
                    )
                )
        notifications = SqlAlchemyNotificationRepository(session)
        notification = Notification(
            id=uuid4(),
            user_id=owner,
            reminder_id=reminder.id,
            source="personal",
            event_id=event_id,
            title="Study",
            starts_at=reminder.starts_at,
            created_at=now,
        )
        notifications.create_once(notification)
        notifications.create_once(replace(notification, id=uuid4()))
        assert notifications.list(owner, True, 100, 0) == [notification]
        assert notifications.list(other, False, 100, 0) == []
        notifications.mark_read(owner, notification.id, now - timedelta(seconds=1))
        notifications.mark_read(owner, notification.id, now + timedelta(seconds=1))
        assert notifications.get(owner, notification.id) == replace(notification, read_at=now)
        assert notifications.list(owner, True, 100, 0) == []
        session.execute(
            delete(PersonalCalendarEventModel).where(PersonalCalendarEventModel.id == event_id)
        )
        assert repository.get(owner, reminder.id) is None
        assert notifications.get(owner, notification.id) is not None
        session.commit()
    with pytest.raises(RuntimeError, match="must be preserved"):
        command.downgrade(config, "0017_database_calendar_views")
    database_connection.execute(delete(UserModel).where(UserModel.id == owner))
    assert database_connection.scalar(select(NotificationModel.id)) is None
    command.downgrade(config, "0017_database_calendar_views")
    assert "reminders" not in inspect(database_connection).get_table_names()
    command.upgrade(config, "head")
    command.check(config)
