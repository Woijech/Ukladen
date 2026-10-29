from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, defer

from app.modules.tasks.domain.tasks import TaskSummary
from app.modules.tasks.infrastructure.orm import TaskDependencyModel, TaskModel
from app.modules.tasks.infrastructure.repository import task_summary


class SqlAlchemyTaskDependencies:
    def __init__(self, session: Session) -> None:
        self.session = session

    def contains(self, user_id: UUID, task_id: UUID, predecessor_id: UUID) -> bool:
        return (
            self.session.scalar(
                select(TaskDependencyModel.task_id).where(
                    TaskDependencyModel.user_id == user_id,
                    TaskDependencyModel.task_id == task_id,
                    TaskDependencyModel.predecessor_id == predecessor_id,
                )
            )
            is not None
        )

    def reaches(self, user_id: UUID, task_id: UUID, target_id: UUID) -> bool:
        paths = (
            select(TaskDependencyModel.predecessor_id)
            .where(TaskDependencyModel.user_id == user_id, TaskDependencyModel.task_id == task_id)
            .cte("task_dependency_paths", recursive=True)
        )
        paths = paths.union(
            select(TaskDependencyModel.predecessor_id)
            .join(paths, TaskDependencyModel.task_id == paths.c.predecessor_id)
            .where(TaskDependencyModel.user_id == user_id)
        )
        return (
            self.session.scalar(
                select(paths.c.predecessor_id).where(paths.c.predecessor_id == target_id).limit(1)
            )
            is not None
        )

    def put(self, user_id: UUID, task_id: UUID, predecessor_id: UUID) -> None:
        self.session.add(
            TaskDependencyModel(user_id=user_id, task_id=task_id, predecessor_id=predecessor_id)
        )
        self.session.flush()

    def delete(self, user_id: UUID, task_id: UUID, predecessor_id: UUID) -> bool:
        return (
            self.session.scalar(
                delete(TaskDependencyModel)
                .where(
                    TaskDependencyModel.user_id == user_id,
                    TaskDependencyModel.task_id == task_id,
                    TaskDependencyModel.predecessor_id == predecessor_id,
                )
                .returning(TaskDependencyModel.task_id)
            )
            is not None
        )

    def list(self, user_id: UUID, task_id: UUID, limit: int, offset: int) -> list[TaskSummary]:
        query = (
            select(TaskModel)
            .join(TaskDependencyModel, TaskModel.id == TaskDependencyModel.predecessor_id)
            .where(
                TaskDependencyModel.user_id == user_id,
                TaskDependencyModel.task_id == task_id,
                TaskModel.user_id == user_id,
            )
            .options(defer(TaskModel.description))
            .order_by(TaskModel.created_at, TaskModel.id)
            .limit(limit)
            .offset(offset)
            .execution_options(populate_existing=True)
        )
        return [task_summary(row) for row in self.session.scalars(query)]

    def has_unresolved(self, user_id: UUID, task_id: UUID) -> bool:
        return (
            self.session.scalar(
                select(TaskModel.id)
                .join(TaskDependencyModel, TaskModel.id == TaskDependencyModel.predecessor_id)
                .where(
                    TaskDependencyModel.user_id == user_id,
                    TaskDependencyModel.task_id == task_id,
                    TaskModel.user_id == user_id,
                    (TaskModel.status != "done") | TaskModel.trashed_at.is_not(None),
                )
                .limit(1)
            )
            is not None
        )
