from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.tasks.domain.tasks import (
    InvalidTaskInput,
    TaskPriority,
    TaskStatus,
    TaskSummary,
    task_values,
)


class TaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("title", mode="before", check_fields=False)
    @classmethod
    def trim_title(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("deadline_at", mode="before", check_fields=False)
    @classmethod
    def exact_deadline(cls, value: object) -> object:
        if value is not None and not (
            isinstance(value, datetime) or (isinstance(value, str) and "T" in value)
        ):
            raise InvalidTaskInput()
        return value


class TaskCreate(TaskInput):
    title: str = Field(min_length=1, max_length=200, strict=True)
    description: str | None = Field(default=None, max_length=10000, strict=True)
    status: TaskStatus = "todo"
    priority: TaskPriority = "normal"
    deadline_at: AwareDatetime | None = None
    estimated_minutes: int | None = Field(default=None, ge=1, le=525600, strict=True)
    parent_id: UUID | None = None

    @model_validator(mode="after")
    def validate_values(self) -> Self:
        task_values(self.model_dump())
        return self


class TaskPatch(TaskInput):
    expected_version: int = Field(ge=1, le=2**31 - 2, strict=True)
    title: str | None = Field(default=None, min_length=1, max_length=200, strict=True)
    description: str | None = Field(default=None, max_length=10000, strict=True)
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    deadline_at: AwareDatetime | None = None
    estimated_minutes: int | None = Field(default=None, ge=1, le=525600, strict=True)
    parent_id: UUID | None = None

    @model_validator(mode="after")
    def validate_changes(self) -> Self:
        changes = self.model_dump(exclude_unset=True, exclude={"expected_version"})
        if not changes:
            raise InvalidTaskInput()
        task_values({"title": "Task"} | changes)
        return self


class TaskVersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1, le=2**31 - 2, strict=True)


class TaskSummaryResponse(BaseModel):
    id: UUID
    parent_id: UUID | None
    title: str
    status: TaskStatus
    priority: TaskPriority
    deadline_at: AwareDatetime | None
    estimated_minutes: int | None
    version: int
    created_at: AwareDatetime
    updated_at: AwareDatetime
    trashed_at: AwareDatetime | None
    trash_batch_id: UUID | None
    is_overdue: bool

    @classmethod
    def from_task(cls, task: TaskSummary, now: datetime) -> Self:
        return cls.model_validate(
            {field: getattr(task, field) for field in cls.model_fields if field != "is_overdue"}
            | {"is_overdue": task.is_overdue(now)}
        )


class TaskResponse(TaskSummaryResponse):
    description: str | None


class TaskListResponse(BaseModel):
    items: list[TaskSummaryResponse]
    limit: int
    offset: int


class TaskDependencyListResponse(TaskListResponse):
    has_unresolved_dependencies: bool
