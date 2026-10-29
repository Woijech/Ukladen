from dataclasses import replace
from typing import Protocol
from uuid import UUID

from app.modules.tasks.application.service import TaskService
from app.modules.tasks.domain.tasks import (
    InvalidTaskInput,
    Task,
    TaskSummary,
    TaskTrashConflict,
    require_task_version,
)


class TaskDependencyConflict(Exception):
    pass


class TaskDependencies(Protocol):
    def contains(self, user_id: UUID, task_id: UUID, predecessor_id: UUID) -> bool: ...
    def reaches(self, user_id: UUID, task_id: UUID, target_id: UUID) -> bool: ...
    def put(self, user_id: UUID, task_id: UUID, predecessor_id: UUID) -> None: ...
    def delete(self, user_id: UUID, task_id: UUID, predecessor_id: UUID) -> bool: ...
    def list(self, user_id: UUID, task_id: UUID, limit: int, offset: int) -> list[TaskSummary]: ...
    def has_unresolved(self, user_id: UUID, task_id: UUID) -> bool: ...


class TaskDependencyService:
    """Dependency edits share the ordinary owner write lock and task version."""

    def __init__(self, tasks: TaskService, repository: TaskDependencies) -> None:
        self.tasks, self.repository = tasks, repository

    def change(
        self,
        user_id: UUID,
        task_id: UUID,
        predecessor_id: UUID,
        expected_version: int,
        *,
        remove: bool = False,
    ) -> Task:
        self.tasks._require_user(user_id, write=True)
        current = self.tasks.get(user_id, task_id)
        require_task_version(current.version, expected_version)
        if current.trashed_at is not None:
            raise TaskTrashConflict()
        predecessor = self.tasks.get(user_id, predecessor_id)
        if remove:
            changed = self.repository.delete(user_id, task_id, predecessor_id)
        else:
            if predecessor.trashed_at is not None:
                raise TaskTrashConflict()
            if task_id == predecessor_id or self.repository.reaches(
                user_id, predecessor_id, task_id
            ):
                raise TaskDependencyConflict()
            changed = not self.repository.contains(user_id, task_id, predecessor_id)
            if changed:
                self.repository.put(user_id, task_id, predecessor_id)
        if not changed:
            return current
        updated = replace(current, version=current.version + 1, updated_at=self.tasks.now())
        self.tasks.repository.save(updated, expected_version)
        return updated

    def list(
        self, user_id: UUID, task_id: UUID, limit: int = 100, offset: int = 0
    ) -> tuple[list[TaskSummary], bool]:
        self.tasks.get(user_id, task_id)
        if (
            type(limit) is not int
            or not 1 <= limit <= 200
            or type(offset) is not int
            or not 0 <= offset <= 2**31 - 1
        ):
            raise InvalidTaskInput()
        return (
            self.repository.list(user_id, task_id, limit, offset),
            self.repository.has_unresolved(user_id, task_id),
        )
