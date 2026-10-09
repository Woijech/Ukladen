from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class PersonalCalendarEventModel(Base):
    __tablename__ = "personal_calendar_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_busy: Mapped[bool] = mapped_column(server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("title ~ '[^[:space:]]'", name="ck_personal_calendar_events_title"),
        CheckConstraint("ends_at > starts_at", name="ck_personal_calendar_events_interval"),
        Index("ix_personal_calendar_events_user_start", "user_id", "starts_at", "id"),
    )
