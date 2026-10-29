import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol
from uuid import UUID, uuid4, uuid5

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.modules.calendar.domain.availability import TimeInterval, merge_intervals
from app.modules.tasks.application.planning import PlanningService
from app.modules.tasks.domain.planner import plan_work
from app.modules.tasks.domain.planning import WorkSession
from app.modules.tasks.domain.tasks import (
    InvalidTaskInput,
    TaskNotFound,
    TaskSummary,
    TaskVersionConflict,
)


class PlanInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class DatedWindow(PlanInput):
    starts_at: AwareDatetime
    ends_at: AwareDatetime

    @field_validator("starts_at", "ends_at", mode="before")
    @classmethod
    def explicit_datetime(cls, value: object) -> object:
        if not isinstance(value, datetime) and not (isinstance(value, str) and "T" in value):
            raise ValueError("An explicit offset-aware timestamp is required.")
        return value


class PlanRequest(DatedWindow):
    task_ids: tuple[UUID, ...] = Field(min_length=1, max_length=100)
    windows: tuple[DatedWindow, ...] | None = Field(default=None, max_length=256)
    replan: bool = Field(default=False, strict=True)


class SessionPlacement(DatedWindow):
    task_id: UUID
    retained_id: UUID | None = None


class ExistingSession(DatedWindow):
    id: UUID
    task_id: UUID
    pinned: bool
    version: int


class Unplaced(PlanInput):
    task_id: UUID
    minutes: int | None
    reason: str


class PlanPreview(PlanInput):
    id: UUID
    created_at: AwareDatetime
    expires_at: AwareDatetime
    request: PlanRequest
    timezone: str
    fingerprint: str
    digest: str
    sessions: tuple[SessionPlacement, ...]
    task_titles: dict[str, str] = Field(default_factory=dict)
    previous_sessions: tuple[ExistingSession, ...] = ()
    protected_sessions: tuple[ExistingSession, ...] = ()
    cancelled_sessions: tuple[UUID, ...]
    unplaced: tuple[Unplaced, ...]
    warnings: tuple[str, ...]
    verified: bool
    status: Literal["pending", "applied", "rejected", "expired"] = "pending"


class PlanRepository(Protocol):
    def facts(
        self, user_id: UUID, now: datetime
    ) -> tuple[list[TaskSummary], list[tuple[UUID, UUID]], list[WorkSession]]: ...
    def get(self, user_id: UUID, plan_id: UUID) -> PlanPreview | None: ...
    def put(self, user_id: UUID, preview: PlanPreview) -> None: ...


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, default=str, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


class PlanService:
    """Durable exact preview and receipt in the caller's shared transaction."""

    def __init__(
        self,
        planning: PlanningService,
        repository: PlanRepository,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self.planning, self.repository, self.now = planning, repository, now

    def preview(
        self,
        user_id: UUID,
        request: PlanRequest,
        *,
        plan_id: UUID | None = None,
        created_at: datetime | None = None,
    ) -> PlanPreview:
        self.planning.tasks._require_user(user_id)
        now = created_at or self.now()
        span = TimeInterval(request.starts_at, request.ends_at)
        if (
            span.starts_at <= now
            or span.ends_at - span.starts_at > timedelta(days=31)
            or len(set(request.task_ids)) != len(request.task_ids)
        ):
            raise InvalidTaskInput()
        preferences = self.planning.preferences(user_id)
        tasks, dependencies, future = self.repository.facts(user_id, now)
        by_id = {task.id: task for task in tasks}
        if any(identifier not in by_id for identifier in request.task_ids):
            raise TaskNotFound()
        selected = set(request.task_ids)
        # Include descendants exactly once; the domain planner allocates leaf effort only.
        for _ in range(len(tasks)):
            expanded = selected | {
                task.id for task in tasks if task.parent_id in selected and task.trashed_at is None
            }
            if expanded == selected:
                break
            selected = expanded
        movable = [
            item
            for item in future
            if request.replan
            and item.task_id in selected
            and not item.pinned
            and not item.cancelled
            and item.starts_at > now
            and item.starts_at >= span.starts_at
            and item.ends_at <= span.ends_at
        ]
        movable_ids = frozenset(item.id for item in movable)
        fixed = [item for item in future if not item.cancelled and item.id not in movable_ids]
        selected_fixed = [item for item in fixed if item.task_id in selected]
        if len(movable) + len(selected_fixed) > 1024:
            raise InvalidTaskInput("Too many existing sessions; narrow the selected tasks.")
        availability = self.planning.availability.read(
            user_id,
            span.starts_at,
            span.ends_at,
            [],
            minimum_minutes=1,
            exclude_work_session_ids=movable_ids,
        )
        windows = (
            [TimeInterval(item.starts_at, item.ends_at) for item in request.windows]
            if request.windows is not None
            else preferences.expand(span.starts_at, span.ends_at, availability.timezone)
        )
        if any(item.starts_at < span.starts_at or item.ends_at > span.ends_at for item in windows):
            raise InvalidTaskInput()
        warnings = list(availability.warnings)
        if not windows:
            warnings.append("work_windows_required")
        result = plan_work(
            tasks,
            dependencies,
            set(request.task_ids),
            merge_intervals(windows),
            availability.occupied,
            fixed,
            movable,
            preferences,
            self.now(),
        )
        retained = {item.retained_id for item in result.sessions if item.retained_id is not None}
        state = fingerprint(
            {
                "availability": availability.snapshot,
                "tasks": [asdict(item) for item in tasks],
                "dependencies": dependencies,
                "sessions": [asdict(item) for item in future],
                "preferences": asdict(preferences),
            }
        )
        preview = PlanPreview(
            id=plan_id or uuid4(),
            created_at=now,
            expires_at=now + timedelta(hours=24),
            request=request,
            timezone=availability.timezone,
            fingerprint=state,
            digest="",
            sessions=tuple(SessionPlacement(**asdict(item)) for item in result.sessions),
            task_titles={str(identifier): by_id[identifier].title for identifier in selected},
            previous_sessions=tuple(
                ExistingSession(**{key: getattr(item, key) for key in ExistingSession.model_fields})
                for item in movable
            ),
            protected_sessions=tuple(
                ExistingSession(**{key: getattr(item, key) for key in ExistingSession.model_fields})
                for item in selected_fixed
            ),
            cancelled_sessions=tuple(item.id for item in movable if item.id not in retained),
            unplaced=tuple(Unplaced(**asdict(item)) for item in result.unplaced),
            warnings=tuple(warnings),
            verified=availability.verified and bool(windows),
        )
        return preview.model_copy(
            update={
                "digest": fingerprint(preview.model_dump(mode="json", exclude={"digest", "status"}))
            }
        )

    def propose(self, user_id: UUID, request: PlanRequest) -> PlanPreview:
        preview = self.preview(user_id, request)
        self.repository.put(user_id, preview)
        return preview

    def get(self, user_id: UUID, plan_id: UUID) -> PlanPreview:
        self.planning.tasks._require_user(user_id)
        preview = self.repository.get(user_id, plan_id)
        if preview is None:
            raise TaskNotFound()
        return preview

    def validate(self, user_id: UUID, plan_id: UUID, digest: str) -> PlanPreview:
        self.planning.tasks._require_user(user_id, write=True)
        self.planning.repository.lock_schedule(user_id)
        stored = self.get(user_id, plan_id)
        if stored.digest != digest:
            raise TaskVersionConflict()
        if stored.status == "applied":
            return stored
        if (
            stored.status != "pending"
            or stored.expires_at <= self.now()
            or stored.request.starts_at <= self.now()
        ):
            raise TaskVersionConflict()
        current = self.preview(
            user_id, stored.request, plan_id=stored.id, created_at=stored.created_at
        )
        if current.digest != stored.digest:
            raise TaskVersionConflict()
        return current

    def apply(
        self, user_id: UUID, plan_id: UUID, digest: str, *, accept_partial: bool = False
    ) -> PlanPreview:
        preview = self.validate(user_id, plan_id, digest)
        if preview.status == "applied":
            return preview
        if not preview.verified or (preview.unplaced and not accept_partial):
            raise TaskVersionConflict()
        for identifier in preview.cancelled_sessions:
            current = self.planning.session(user_id, identifier)
            self.planning.repository.put_session(
                replace(current, cancelled=True, version=current.version + 1)
            )
        for index, item in enumerate(preview.sessions):
            if item.retained_id is None:
                self.planning.repository.put_session(
                    WorkSession(
                        id=uuid5(preview.id, str(index)),
                        user_id=user_id,
                        task_id=item.task_id,
                        starts_at=item.starts_at,
                        ends_at=item.ends_at,
                    )
                )
        applied = preview.model_copy(update={"status": "applied"})
        self.repository.put(user_id, applied)
        return applied
