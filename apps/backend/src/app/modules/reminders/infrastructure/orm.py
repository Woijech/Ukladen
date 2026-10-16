from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ReminderModel(Base):
    __tablename__ = "reminders"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    personal_event_id: Mapped[UUID | None]
    official_event_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("official_schedule_events.id", ondelete="CASCADE")
    )
    minutes_before: Mapped[int] = mapped_column(Integer)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(9))
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["personal_event_id", "user_id"],
            ["personal_calendar_events.id", "personal_calendar_events.user_id"],
            ondelete="CASCADE",
            name="fk_reminders_personal_owner",
        ),
        CheckConstraint(
            "num_nonnulls(personal_event_id, official_event_id) = 1", name="ck_reminders_target"
        ),
        CheckConstraint("minutes_before BETWEEN 0 AND 43200", name="ck_reminders_offset"),
        CheckConstraint("version > 0", name="ck_reminders_version"),
        CheckConstraint(
            "due_at = starts_at - minutes_before * interval '1 minute'",
            name="ck_reminders_trigger",
        ),
        CheckConstraint(
            "status IN ('pending', 'delivered', 'cancelled')", name="ck_reminders_status"
        ),
        Index("ix_reminders_due", "due_at", "id", postgresql_where="status = 'pending'"),
        Index("ix_reminders_owner", "user_id", "created_at", "id"),
        Index("ix_reminders_personal", "personal_event_id"),
        Index("ix_reminders_official", "official_event_id"),
    )
