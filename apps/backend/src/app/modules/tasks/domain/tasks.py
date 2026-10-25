from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, TypedDict, cast
from uuid import UUID

TaskStatus = Literal["todo", "in_progress", "done", "cancelled"]
TaskPriority = Literal["low", "normal", "high", "urgent"]
STATUSES = ("todo", "in_progress", "done", "cancelled")
PRIORITIES = ("low", "normal", "high", "urgent")
TASK_FIELDS = {
    "title",
    "description",
    "status",
    "priority",
    "deadline_at",
    "estimated_minutes",
    "parent_id",
}


class InvalidTaskInput(ValueError):
    pass


class TaskNotFound(Exception):
    pass


class TaskVersionConflict(Exception):
    pass


class TaskHierarchyConflict(Exception):
    pass


class TaskValues(TypedDict):
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    deadline_at: datetime | None
    estimated_minutes: int | None
    parent_id: UUID | None


def task_text(value: object, limit: int, *, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise InvalidTaskInput()
    if required:
        value = value.strip()
    if (required and not value) or len(value) > limit or "\x00" in value:
        raise InvalidTaskInput()
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise InvalidTaskInput() from None
    return value


def task_values(values: Mapping[str, object]) -> TaskValues:
    if values.keys() - TASK_FIELDS:
        raise InvalidTaskInput()
    title = task_text(values.get("title"), 200, required=True)
    assert title is not None
    status, priority = values.get("status", "todo"), values.get("priority", "normal")
    if not isinstance(status, str) or status not in STATUSES:
        raise InvalidTaskInput()
    if not isinstance(priority, str) or priority not in PRIORITIES:
        raise InvalidTaskInput()
    deadline = values.get("deadline_at")
    if deadline is not None:
        if not isinstance(deadline, datetime) or deadline.utcoffset() is None:
            raise InvalidTaskInput()
        try:
            deadline = deadline.astimezone(UTC)
        except ValueError, OverflowError:
            raise InvalidTaskInput() from None
    effort = values.get("estimated_minutes")
    if effort is not None and (type(effort) is not int or not 1 <= effort <= 525600):
        raise InvalidTaskInput()
    parent_id = values.get("parent_id")
    if parent_id is not None and not isinstance(parent_id, UUID):
        raise InvalidTaskInput()
    return TaskValues(
        title=title,
        description=task_text(values.get("description"), 10000),
        status=cast(TaskStatus, status),
        priority=cast(TaskPriority, priority),
        deadline_at=deadline,
        estimated_minutes=cast(int | None, effort),
        parent_id=cast(UUID | None, parent_id),
    )


def require_task_version(actual: int, expected: int) -> None:
    if type(expected) is not int or not 1 <= expected <= 2**31 - 2:
        raise InvalidTaskInput()
    if actual != expected:
        raise TaskVersionConflict()


@dataclass(frozen=True, kw_only=True)
class TaskSummary:
    id: UUID
    user_id: UUID
    title: str
    status: TaskStatus
    priority: TaskPriority
    deadline_at: datetime | None
    estimated_minutes: int | None
    version: int
    created_at: datetime
    updated_at: datetime
    parent_id: UUID | None = None
    trashed_at: datetime | None = None
    trash_batch_id: UUID | None = None

    def is_overdue(self, now: datetime) -> bool:
        return (
            self.status in ("todo", "in_progress")
            and self.deadline_at is not None
            and self.deadline_at < now
        )


@dataclass(frozen=True, kw_only=True)
class Task(TaskSummary):
    description: str | None
