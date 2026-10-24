from dataclasses import asdict
from typing import cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session, defer

from app.modules.tasks.domain.tasks import (
    Task,
    TaskPriority,
    TaskStatus,
    TaskSummary,
    TaskVersionConflict,
)
from app.modules.tasks.infrastructure.orm import TaskModel


def task_summary(row: TaskModel) -> TaskSummary:
    return TaskSummary(
        id=row.id,
        user_id=row.user_id,
        parent_id=row.parent_id,
        title=row.title,
        status=cast(TaskStatus, row.status),
        priority=cast(TaskPriority, row.priority),
        deadline_at=row.deadline_at,
        estimated_minutes=row.estimated_minutes,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyTaskRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, task: Task) -> None:
        self.session.add(TaskModel(**asdict(task)))
        self.session.flush()

    def get(self, user_id: UUID, task_id: UUID) -> Task | None:
        row = self.session.scalar(
            select(TaskModel)
            .where(TaskModel.user_id == user_id, TaskModel.id == task_id)
            .execution_options(populate_existing=True)
        )
        return Task(**asdict(task_summary(row)), description=row.description) if row else None

    def list(
        self,
        user_id: UUID,
        status: TaskStatus | None,
        priority: TaskPriority | None,
        limit: int,
        offset: int,
        parent_id: UUID | None = None,
        roots_only: bool = False,
    ) -> list[TaskSummary]:
        query = (
            select(TaskModel)
            .options(defer(TaskModel.description))
            .where(TaskModel.user_id == user_id)
        )
        if status is not None:
            query = query.where(TaskModel.status == status)
        if priority is not None:
            query = query.where(TaskModel.priority == priority)
        if parent_id is not None:
            query = query.where(TaskModel.parent_id == parent_id)
        elif roots_only:
            query = query.where(TaskModel.parent_id.is_(None))
        return [
            task_summary(row)
            for row in self.session.scalars(
                query.order_by(TaskModel.created_at, TaskModel.id)
                .limit(limit)
                .offset(offset)
                .execution_options(populate_existing=True)
            )
        ]

    def save(self, task: Task, expected_version: int) -> None:
        values = asdict(task)
        for field in ("id", "user_id", "created_at"):
            values.pop(field)
        identifier = self.session.scalar(
            update(TaskModel)
            .where(
                TaskModel.id == task.id,
                TaskModel.user_id == task.user_id,
                TaskModel.version == expected_version,
            )
            .values(**values)
            .returning(TaskModel.id)
        )
        if identifier is None:
            raise TaskVersionConflict()

    def has_open_descendants(self, user_id: UUID, task_id: UUID) -> bool:
        descendants = (
            select(TaskModel.id)
            .where(TaskModel.user_id == user_id, TaskModel.parent_id == task_id)
            .cte("task_descendants", recursive=True)
        )
        descendants = descendants.union(
            select(TaskModel.id)
            .join(descendants, TaskModel.parent_id == descendants.c.id)
            .where(TaskModel.user_id == user_id)
        )
        return (
            self.session.scalar(
                select(TaskModel.id)
                .where(
                    TaskModel.user_id == user_id,
                    TaskModel.id.in_(select(descendants.c.id)),
                    TaskModel.status.in_(("todo", "in_progress")),
                )
                .limit(1)
            )
            is not None
        )
