from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, synonym

from app.db.session import Base


class PersonalCalendarEventModel(Base):
    __tablename__ = "personal_calendar_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    calendar_id: Mapped[UUID | None]
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(10000))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    location: Mapped[str | None] = mapped_column(String(500))
    blocks_time: Mapped[bool] = mapped_column(Boolean, server_default="true")
    is_busy: Mapped[bool] = synonym("blocks_time")
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_personal_calendar_events_id_user"),
        ForeignKeyConstraint(
            ["calendar_id", "user_id"],
            ["personal_calendars.id", "personal_calendars.user_id"],
            name="fk_event_personal_calendar",
        ),
        Index("ix_personal_events_calendar", "user_id", "calendar_id"),
        CheckConstraint("ends_at > starts_at", name="ck_personal_calendar_events_time"),
        CheckConstraint("version > 0", name="ck_personal_calendar_events_version"),
        CheckConstraint(
            "char_length(title) BETWEEN 1 AND 200 AND title !~ '^[[:space:]]|[[:space:]]$'",
            name="ck_personal_calendar_events_title",
        ),
        Index("ix_personal_calendar_events_user_time", "user_id", "starts_at"),
    )


class ScheduleOverrideModel(Base):
    __tablename__ = "schedule_overrides"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    official_event_id: Mapped[UUID] = mapped_column(
        ForeignKey("official_schedule_events.id"), primary_key=True
    )
    hidden: Mapped[bool] = mapped_column(Boolean, server_default="false")
    skipped: Mapped[bool] = mapped_column(Boolean, server_default="false")
    title: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(10000))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    location: Mapped[str | None] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "(starts_at IS NULL AND ends_at IS NULL) OR "
            "(starts_at IS NOT NULL AND ends_at IS NOT NULL AND ends_at > starts_at)",
            name="ck_schedule_overrides_time",
        ),
        CheckConstraint("version > 0", name="ck_schedule_overrides_version"),
        CheckConstraint(
            "title IS NULL OR (char_length(title) BETWEEN 1 AND 200 "
            "AND title !~ '^[[:space:]]|[[:space:]]$')",
            name="ck_schedule_overrides_title",
        ),
        Index("ix_schedule_overrides_user_time", "user_id", "starts_at"),
    )


class PersonalCalendarModel(Base):
    __tablename__ = "personal_calendars"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    color: Mapped[str] = mapped_column(String(7))
    version: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_personal_calendars_owner"),
        CheckConstraint("version > 0", name="ck_personal_calendars_version"),
        CheckConstraint(
            "char_length(btrim(name)) BETWEEN 1 AND 100", name="ck_personal_calendars_name"
        ),
        CheckConstraint("color ~ '^#[0-9a-f]{6}$'", name="ck_personal_calendars_color"),
    )


class CalendarVisibilityModel(Base):
    __tablename__ = "calendar_visibility"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[int]
    default_visible: Mapped[bool]
    hidden_calendar_ids: Mapped[list] = mapped_column(JSONB)
    hidden_lesson_types: Mapped[list] = mapped_column(JSONB)
    __table_args__ = (CheckConstraint("version > 0", name="ck_calendar_visibility_version"),)
