from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.modules.tasks.application.ports import TaskRepository
from app.modules.tasks.domain.tasks import (
    PRIORITIES,
    STATUSES,
    TASK_FIELDS,
    InvalidTaskInput,
    Task,
    TaskNotFound,
    TaskPriority,
    TaskStatus,
    TaskSummary,
    require_task_version,
    task_values,
)
from app.modules.users.application.ports import UserAuthentication
from app.modules.users.domain.profile import ProfileUnavailable


class TaskService:
    """Standalone task operations; the caller owns transactions and commits."""

    def __init__(
        self,
        repository: TaskRepository,
        users: UserAuthentication,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.repository, self.users, self.now = repository, users, now

    def _require_user(self, user_id: UUID, *, write: bool = False) -> None:
        active = self.users.lock_active(user_id) if write else self.users.is_active(user_id)
        if not active:
            raise ProfileUnavailable()

    def create(self, user_id: UUID, values: Mapping[str, object]) -> Task:
        self._require_user(user_id, write=True)
        normalized = task_values(values)
        now = self.now()
        task = Task(
            id=uuid4(), user_id=user_id, version=1, created_at=now, updated_at=now, **normalized
        )
        self.repository.create(task)
        return task

    def get(self, user_id: UUID, task_id: UUID) -> Task:
        self._require_user(user_id)
        task = self.repository.get(user_id, task_id)
        if task is None:
            raise TaskNotFound()
        return task

    def list(
        self,
        user_id: UUID,
        *,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TaskSummary]:
        self._require_user(user_id)
        if (
            type(limit) is not int
            or not 1 <= limit <= 200
            or type(offset) is not int
            or not 0 <= offset <= 2**31 - 1
            or (status is not None and status not in STATUSES)
            or (priority is not None and priority not in PRIORITIES)
        ):
            raise InvalidTaskInput()
        return self.repository.list(user_id, status, priority, limit, offset)

    def update(
        self,
        user_id: UUID,
        task_id: UUID,
        changes: Mapping[str, object],
        expected_version: int,
    ) -> Task:
        self._require_user(user_id, write=True)
        current = self.repository.get(user_id, task_id)
        if current is None:
            raise TaskNotFound()
        require_task_version(current.version, expected_version)
        if not changes or changes.keys() - TASK_FIELDS:
            raise InvalidTaskInput()
        values = {field: getattr(current, field) for field in TASK_FIELDS} | dict(changes)
        task = replace(
            current, **task_values(values), version=current.version + 1, updated_at=self.now()
        )
        self.repository.save(task, expected_version)
        return task
