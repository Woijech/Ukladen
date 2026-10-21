from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class TaskModel(Base):
    __tablename__ = "tasks"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), server_default="todo")
    priority: Mapped[str] = mapped_column(String(16), server_default="normal")
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estimated_minutes: Mapped[int | None]
    version: Mapped[int] = mapped_column(server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "char_length(title) BETWEEN 1 AND 200 AND title = btrim(title) "
            "AND title ~ '[^[:space:]]'",
            name="ck_tasks_title",
        ),
        CheckConstraint("char_length(description) <= 10000", name="ck_tasks_description"),
        CheckConstraint(
            "status IN ('todo', 'in_progress', 'done', 'cancelled')", name="ck_tasks_status"
        ),
        CheckConstraint(
            "priority IN ('low', 'normal', 'high', 'urgent')", name="ck_tasks_priority"
        ),
        CheckConstraint("estimated_minutes BETWEEN 1 AND 525600", name="ck_tasks_effort"),
        CheckConstraint("version > 0", name="ck_tasks_version"),
        Index("ix_tasks_owner_created", "user_id", "created_at", "id"),
    )
