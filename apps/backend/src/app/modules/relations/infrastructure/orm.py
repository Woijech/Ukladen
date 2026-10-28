from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class CalendarPageLinkModel(Base):
    __tablename__ = "page_calendar_links"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    page_id: Mapped[UUID] = mapped_column()
    personal_event_id: Mapped[UUID | None] = mapped_column()
    official_event_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("official_schedule_events.id")
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(
            ["page_id", "user_id"],
            ["note_pages.id", "note_pages.user_id"],
            ondelete="CASCADE",
            name="fk_page_calendar_links_page_owner",
        ),
        ForeignKeyConstraint(
            ["personal_event_id", "user_id"],
            ["personal_calendar_events.id", "personal_calendar_events.user_id"],
            ondelete="CASCADE",
            name="fk_page_calendar_links_event_owner",
        ),
        CheckConstraint(
            "(personal_event_id IS NULL) != (official_event_id IS NULL)",
            name="ck_page_calendar_links_target",
        ),
        UniqueConstraint("page_id", "personal_event_id", name="uq_page_calendar_links_personal"),
        UniqueConstraint("page_id", "official_event_id", name="uq_page_calendar_links_official"),
        Index("ix_page_calendar_links_user_page", "user_id", "page_id", "created_at", "id"),
        Index(
            "ix_page_calendar_links_user_personal",
            "user_id",
            "personal_event_id",
            "created_at",
            "id",
        ),
        Index(
            "ix_page_calendar_links_user_official",
            "user_id",
            "official_event_id",
            "created_at",
            "id",
        ),
    )


class PageMaterialLinkModel(Base):
    __tablename__ = "page_material_links"

    page_id: Mapped[UUID] = mapped_column(primary_key=True)
    material_id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(
            ["page_id", "user_id"],
            ["note_pages.id", "note_pages.user_id"],
            ondelete="CASCADE",
            name="fk_page_material_links_page_owner",
        ),
        ForeignKeyConstraint(
            ["material_id", "user_id"],
            ["materials.id", "materials.user_id"],
            ondelete="CASCADE",
            name="fk_page_material_links_material_owner",
        ),
        Index("ix_page_material_links_reverse", "user_id", "material_id", "page_id"),
    )


class TaskPageLinkModel(Base):
    __tablename__ = "task_page_links"

    task_id: Mapped[UUID] = mapped_column(primary_key=True)
    page_id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(
            ["task_id", "user_id"],
            ["tasks.id", "tasks.user_id"],
            name="fk_task_page_links_task_owner",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["page_id", "user_id"],
            ["note_pages.id", "note_pages.user_id"],
            name="fk_task_page_links_page_owner",
            ondelete="CASCADE",
        ),
        Index("ix_task_page_links_reverse", "user_id", "page_id", "task_id"),
    )
