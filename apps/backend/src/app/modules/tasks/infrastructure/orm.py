from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class TaskModel(Base):
    __tablename__ = "tasks"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    parent_id: Mapped[UUID | None] = mapped_column()
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), server_default="todo")
    priority: Mapped[str] = mapped_column(String(16), server_default="normal")
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estimated_minutes: Mapped[int | None]
    remaining_minutes: Mapped[int | None]
    version: Mapped[int] = mapped_column(server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trash_batch_id: Mapped[UUID | None] = mapped_column()

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
        CheckConstraint("remaining_minutes BETWEEN 0 AND 525600", name="ck_tasks_remaining"),
        CheckConstraint("version > 0", name="ck_tasks_version"),
        Index("ix_tasks_owner_created", "user_id", "created_at", "id"),
        UniqueConstraint("id", "user_id", name="uq_tasks_id_user"),
        ForeignKeyConstraint(
            ["parent_id", "user_id"],
            ["tasks.id", "tasks.user_id"],
            name="fk_tasks_parent_owner",
        ),
        CheckConstraint("parent_id IS NULL OR parent_id != id", name="ck_tasks_parent"),
        Index("ix_tasks_owner_parent", "user_id", "parent_id"),
        CheckConstraint("(trashed_at IS NULL) = (trash_batch_id IS NULL)", name="ck_tasks_trash"),
        Index("ix_tasks_owner_trash", "user_id", "trashed_at", "created_at", "id"),
        Index("ix_tasks_owner_trash_batch", "user_id", "trash_batch_id"),
    )


class TaskDependencyModel(Base):
    __tablename__ = "task_dependencies"

    task_id: Mapped[UUID] = mapped_column(primary_key=True)
    predecessor_id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["task_id", "user_id"],
            ["tasks.id", "tasks.user_id"],
            name="fk_task_dependencies_task_owner",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["predecessor_id", "user_id"],
            ["tasks.id", "tasks.user_id"],
            name="fk_task_dependencies_predecessor_owner",
            ondelete="CASCADE",
        ),
        CheckConstraint("task_id != predecessor_id", name="ck_task_dependencies_not_self"),
        Index("ix_task_dependencies_reverse", "user_id", "predecessor_id", "task_id"),
    )
