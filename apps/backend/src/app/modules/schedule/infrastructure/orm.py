from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ScheduleSourceModel(Base):
    __tablename__ = "schedule_sources"

    group_id: Mapped[int] = mapped_column(ForeignKey("university_groups.id"), primary_key=True)
    group_number: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(Text)
    sync_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    __table_args__ = (
        UniqueConstraint("group_number", name="uq_schedule_sources_group_number"),
        CheckConstraint("char_length(group_number) > 0", name="ck_schedule_sources_number"),
        CheckConstraint(
            "status IN ('syncing', 'ready', 'unpublished', 'error', 'unsupported')",
            name="ck_schedule_sources_status",
        ),
        CheckConstraint(
            "(sync_token IS NULL) = (lease_until IS NULL)", name="ck_schedule_sources_lease"
        ),
    )


class OfficialScheduleEventModel(Base):
    __tablename__ = "official_schedule_events"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("schedule_sources.group_id"))
    kind: Mapped[str] = mapped_column(Text)
    subgroup: Mapped[int]
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    subject: Mapped[str | None] = mapped_column(Text)
    subject_full_name: Mapped[str | None] = mapped_column(Text)
    lesson_type: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    rooms: Mapped[list[str]] = mapped_column(JSONB)
    teacher_ids: Mapped[list[int]] = mapped_column(JSONB)
    teacher_names: Mapped[list[str]] = mapped_column(JSONB)
    active: Mapped[bool]

    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_official_schedule_events_time"),
        CheckConstraint("subgroup >= 0", name="ck_official_schedule_events_subgroup"),
        CheckConstraint(
            "kind IN ('lesson', 'exam', 'announcement')", name="ck_official_schedule_events_kind"
        ),
        Index("ix_official_schedule_events_group_time", "group_id", "starts_at"),
    )
