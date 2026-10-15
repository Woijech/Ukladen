from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.modules.reminders.domain.reminders import Reminder, ReminderConflict, ReminderStatus
from app.modules.reminders.infrastructure.orm import ReminderModel


def reminder_entity(row: ReminderModel) -> Reminder:
    event_id = row.personal_event_id or row.official_event_id
    assert event_id is not None
    return Reminder(
        id=row.id,
        user_id=row.user_id,
        source="personal" if row.personal_event_id is not None else "official",
        event_id=event_id,
        minutes_before=row.minutes_before,
        starts_at=row.starts_at,
        due_at=row.due_at,
        status=cast(ReminderStatus, row.status),
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyReminderRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, reminder: Reminder) -> None:
        self.session.add(
            ReminderModel(
                id=reminder.id,
                user_id=reminder.user_id,
                personal_event_id=reminder.event_id if reminder.source == "personal" else None,
                official_event_id=reminder.event_id if reminder.source == "official" else None,
                minutes_before=reminder.minutes_before,
                starts_at=reminder.starts_at,
                due_at=reminder.due_at,
                status=reminder.status,
                version=reminder.version,
                created_at=reminder.created_at,
                updated_at=reminder.updated_at,
            )
        )
        self.session.flush()

    def get(self, user_id: UUID, reminder_id: UUID) -> Reminder | None:
        row = self.session.scalar(
            select(ReminderModel)
            .where(ReminderModel.user_id == user_id, ReminderModel.id == reminder_id)
            .execution_options(populate_existing=True)
        )
        return reminder_entity(row) if row else None

    def list(self, user_id: UUID, limit: int, offset: int) -> list[Reminder]:
        return [
            reminder_entity(row)
            for row in self.session.scalars(
                select(ReminderModel)
                .where(ReminderModel.user_id == user_id)
                .order_by(ReminderModel.created_at.desc(), ReminderModel.id)
                .limit(limit)
                .offset(offset)
            )
        ]

    def save(self, reminder: Reminder, expected_version: int) -> None:
        identifier = self.session.scalar(
            update(ReminderModel)
            .where(
                ReminderModel.user_id == reminder.user_id,
                ReminderModel.id == reminder.id,
                ReminderModel.version == expected_version,
            )
            .values(
                minutes_before=reminder.minutes_before,
                starts_at=reminder.starts_at,
                due_at=reminder.due_at,
                status=reminder.status,
                version=reminder.version,
                updated_at=reminder.updated_at,
            )
            .returning(ReminderModel.id)
        )
        if identifier is None:
            raise ReminderConflict()

    def delete(self, user_id: UUID, reminder_id: UUID) -> None:
        self.session.execute(
            delete(ReminderModel).where(
                ReminderModel.user_id == user_id, ReminderModel.id == reminder_id
            )
        )

    def due(self, now: datetime, limit: int) -> list[tuple[UUID, UUID]]:
        return [
            (row.user_id, row.id)
            for row in self.session.execute(
                select(ReminderModel.user_id, ReminderModel.id)
                .where(ReminderModel.status == "pending", ReminderModel.due_at <= now)
                .order_by(ReminderModel.due_at, ReminderModel.id)
                .limit(limit)
            )
        ]
