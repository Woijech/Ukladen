from dataclasses import asdict
from datetime import datetime
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.notifications.domain.notifications import Notification, NotificationNotFound
from app.modules.notifications.infrastructure.orm import NotificationModel


def notification_entity(row: NotificationModel) -> Notification:
    return Notification(
        id=row.id,
        user_id=row.user_id,
        reminder_id=row.reminder_id,
        source=cast(Literal["personal", "official"], row.source),
        event_id=row.event_id,
        title=row.title,
        starts_at=row.starts_at,
        created_at=row.created_at,
        read_at=row.read_at,
    )


class SqlAlchemyNotificationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_once(self, notification: Notification) -> None:
        self.session.execute(
            insert(NotificationModel)
            .values(**asdict(notification))
            .on_conflict_do_nothing(index_elements=[NotificationModel.reminder_id])
        )

    def get(self, user_id: UUID, notification_id: UUID) -> Notification | None:
        row = self.session.scalar(
            select(NotificationModel)
            .where(NotificationModel.user_id == user_id, NotificationModel.id == notification_id)
            .execution_options(populate_existing=True)
        )
        return notification_entity(row) if row else None

    def list(self, user_id: UUID, unread_only: bool, limit: int, offset: int) -> list[Notification]:
        query = select(NotificationModel).where(NotificationModel.user_id == user_id)
        if unread_only:
            query = query.where(NotificationModel.read_at.is_(None))
        return [
            notification_entity(row)
            for row in self.session.scalars(
                query.order_by(NotificationModel.created_at.desc(), NotificationModel.id)
                .limit(limit)
                .offset(offset)
            )
        ]

    def mark_read(self, user_id: UUID, notification_id: UUID, now: datetime) -> None:
        identifier = self.session.scalar(
            update(NotificationModel)
            .where(NotificationModel.user_id == user_id, NotificationModel.id == notification_id)
            .values(
                read_at=func.coalesce(
                    NotificationModel.read_at, func.greatest(NotificationModel.created_at, now)
                )
            )
            .returning(NotificationModel.id)
        )
        if identifier is None:
            raise NotificationNotFound()
