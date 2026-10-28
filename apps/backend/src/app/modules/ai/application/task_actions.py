from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.search.domain.evidence import SourceReference
from app.modules.tasks.domain.tasks import TaskPriority, TaskStatus, task_values


class TaskDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    title: str = Field(min_length=1, max_length=200, strict=True)
    description: str | None = Field(default=None, max_length=10000, strict=True)
    priority: TaskPriority = "normal"
    deadline_at: AwareDatetime | None = None
    estimated_minutes: int | None = Field(default=None, ge=1, le=525600, strict=True)
    remaining_minutes: int | None = Field(default=None, ge=0, le=525600, strict=True)
    parent_id: UUID | None = None

    @field_validator("deadline_at", mode="before")
    @classmethod
    def explicit_deadline(cls, value: object) -> object:
        if (
            value is not None
            and not isinstance(value, datetime)
            and not (isinstance(value, str) and "T" in value)
        ):
            raise ValueError("An explicit offset-aware timestamp is required.")
        return value

    @model_validator(mode="after")
    def valid_task(self) -> Self:
        task_values(self.model_dump())
        return self


class TaskCreateAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    operation: Literal["task_create"]
    task: TaskDraft
    parent_action: int | None = Field(default=None, ge=0, le=7, strict=True)
    predecessor_ids: tuple[UUID, ...] = Field(default=(), max_length=20)
    predecessor_actions: tuple[Annotated[int, Field(ge=0, le=7, strict=True)], ...] = Field(
        default=(), max_length=7
    )
    sources: tuple[SourceReference, ...] = Field(default=(), max_length=8)
    estimate_kind: Literal["source", "estimate", "unknown"] = "unknown"
    uncertainties: tuple[str, ...] = Field(default=(), max_length=10)
    possible_duplicate_ids: tuple[UUID, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def valid_provenance(self) -> Self:
        if self.parent_action is not None and self.task.parent_id is not None:
            raise ValueError("Select an existing parent or an earlier action.")
        if any(len(text) > 300 or "\x00" in text for text in self.uncertainties):
            raise ValueError("Uncertainty text exceeds the supported bound.")
        if self.task.estimated_minutes is not None and self.estimate_kind == "unknown":
            raise ValueError("Label the duration as source-stated or estimated.")
        if self.estimate_kind == "source" and not self.sources:
            raise ValueError("Source-stated duration requires source evidence.")
        if any(
            source.source not in ("page", "material", "database_record", "task")
            or not source.locator
            or source.locator == "search_snippet"
            for source in self.sources
        ):
            raise ValueError(
                "Extraction needs a real source read and location, not a search snippet."
            )
        return self


class TaskChanges(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    title: str | None = Field(default=None, min_length=1, max_length=200, strict=True)
    description: str | None = Field(default=None, max_length=10000, strict=True)
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    deadline_at: AwareDatetime | None = None
    estimated_minutes: int | None = Field(default=None, ge=1, le=525600, strict=True)
    remaining_minutes: int | None = Field(default=None, ge=0, le=525600, strict=True)
    parent_id: UUID | None = None

    @field_validator("deadline_at", mode="before")
    @classmethod
    def explicit_deadline(cls, value: object) -> object:
        return TaskDraft.explicit_deadline(value)

    @model_validator(mode="after")
    def has_changes(self) -> Self:
        changes = self.model_dump(exclude_unset=True)
        if not changes:
            raise ValueError("Provide explicit task changes.")
        task_values({"title": "Task"} | changes)
        return self


class TaskUpdateAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    operation: Literal["task_update"]
    task_id: UUID
    expected_version: int = Field(ge=1, le=2**31 - 2, strict=True)
    changes: TaskChanges


class PlanApplyAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    operation: Literal["task_plan_apply"]
    plan_id: UUID
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    accept_partial: bool = Field(default=False, strict=True)
