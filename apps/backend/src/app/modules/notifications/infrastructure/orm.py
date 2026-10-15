from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class NotificationModel(Base):
    __tablename__ = "notifications"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # A historical delivery key survives deletion of the reminder or calendar target.
    reminder_id: Mapped[UUID]
    source: Mapped[str] = mapped_column(String(8))
    event_id: Mapped[UUID]
    title: Mapped[str] = mapped_column(String(500))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("reminder_id", name="uq_notifications_reminder"),
        CheckConstraint("source IN ('personal', 'official')", name="ck_notifications_source"),
        CheckConstraint("char_length(title) BETWEEN 1 AND 500", name="ck_notifications_title"),
        CheckConstraint("read_at IS NULL OR read_at >= created_at", name="ck_notifications_read"),
        Index("ix_notifications_owner", "user_id", "created_at", "id"),
    )
