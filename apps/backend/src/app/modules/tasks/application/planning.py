from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from app.modules.calendar.application.availability import (
    CalendarAvailability,
    CalendarAvailabilityService,
)
from app.modules.calendar.application.work_sessions import TaskDeadline, WorkSessionBusy
from app.modules.calendar.domain.availability import TimeInterval
from app.modules.tasks.application.planning_ports import PlanningRepository
from app.modules.tasks.application.service import TaskService
from app.modules.tasks.domain.planning import WorkPreferences, WorkSession
from app.modules.tasks.domain.tasks import (
    InvalidTaskInput,
    TaskNotFound,
    TaskVersionConflict,
    require_task_version,
)


class PlanningService:
    """Caller owns the transaction. Writes serialize with every owner's calendar/task write."""

    def __init__(
        self,
        tasks: TaskService,
        repository: PlanningRepository,
        availability: CalendarAvailabilityService,
    ):
        self.tasks, self.repository, self.availability = tasks, repository, availability

    def preferences(self, user_id: UUID) -> WorkPreferences:
        self.tasks._require_user(user_id)
        return self.repository.preferences(user_id)

    def save_preferences(
        self, user_id: UUID, preferences: WorkPreferences, expected_version: int
    ) -> WorkPreferences:
        self.tasks._require_user(user_id, write=True)
        current = self.repository.preferences(user_id)
        if type(expected_version) is not int or expected_version != current.version:
            raise TaskVersionConflict()
        result = replace(preferences, version=current.version + 1)
        self.repository.save_preferences(user_id, result)
        return result

    def sessions(self, user_id: UUID, starts_at: datetime, ends_at: datetime) -> list[WorkSession]:
        self.tasks._require_user(user_id)
        interval = TimeInterval(starts_at, ends_at)
        if interval.ends_at - interval.starts_at > timedelta(days=366):
            raise InvalidTaskInput()
        return self.repository.sessions(user_id, interval.starts_at, interval.ends_at)

    def calendar(
        self,
        user_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
        *,
        include_sessions: bool = True,
        include_deadlines: bool = False,
    ) -> tuple[list[WorkSessionBusy], list[TaskDeadline]]:
        self.tasks._require_user(user_id)
        interval = TimeInterval(starts_at, ends_at)
        if interval.ends_at - interval.starts_at > timedelta(days=366):
            raise InvalidTaskInput()
        return (
            self.repository.busy(user_id, interval.starts_at, interval.ends_at)
            if include_sessions
            else [],
            self.repository.deadlines(user_id, interval.starts_at, interval.ends_at)
            if include_deadlines
            else [],
        )

    def session(self, user_id: UUID, session_id: UUID) -> WorkSession:
        self.tasks._require_user(user_id)
        current = self.repository.session(user_id, session_id)
        if current is None:
            raise TaskNotFound()
        return current

    def check_session(
        self,
        user_id: UUID,
        task_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
        session_id: UUID | None = None,
    ) -> CalendarAvailability:
        task = self.tasks.get(user_id, task_id)
        if task.trashed_at is not None or task.status not in ("todo", "in_progress"):
            raise InvalidTaskInput()
        interval = TimeInterval(starts_at, ends_at)
        if (
            interval.ends_at - interval.starts_at > timedelta(days=1)
            or (interval.ends_at - interval.starts_at).total_seconds() % 60 != 0
            or interval.starts_at <= self.tasks.now()
        ):
            raise InvalidTaskInput()
        if session_id is not None:
            current = self.session(user_id, session_id)
            if (
                current.task_id != task_id
                or current.cancelled
                or current.starts_at <= self.tasks.now()
            ):
                raise TaskVersionConflict()
        return self.availability.read(
            user_id,
            interval.starts_at,
            interval.ends_at,
            [interval],
            minimum_minutes=1,
            candidates=[interval],
            exclude_work_session_ids=frozenset([session_id]) if session_id else frozenset(),
        )

    def save_session(
        self,
        user_id: UUID,
        task_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
        *,
        snapshot: str,
        pinned: bool = False,
        acknowledge_conflicts: bool = False,
        session_id: UUID | None = None,
        expected_version: int | None = None,
    ) -> WorkSession:
        self.tasks._require_user(user_id, write=True)
        self.repository.lock_schedule(user_id)
        if type(pinned) is not bool or type(acknowledge_conflicts) is not bool:
            raise InvalidTaskInput()
        current = self.session(user_id, session_id) if session_id else None
        if current is not None:
            require_task_version(
                current.version, expected_version if expected_version is not None else 0
            )
        availability = self.check_session(user_id, task_id, starts_at, ends_at, session_id)
        if availability.snapshot != snapshot or (
            (availability.occupied or not availability.verified) and not acknowledge_conflicts
        ):
            raise TaskVersionConflict()
        interval = TimeInterval(starts_at, ends_at)
        result = WorkSession(
            id=current.id if current else uuid4(),
            user_id=user_id,
            task_id=task_id,
            starts_at=interval.starts_at,
            ends_at=interval.ends_at,
            pinned=pinned,
            version=current.version + 1 if current else 1,
        )
        self.repository.put_session(result)
        return result

    def change_session(
        self,
        user_id: UUID,
        session_id: UUID,
        expected_version: int,
        *,
        pinned: bool | None = None,
        cancel: bool = False,
    ) -> WorkSession:
        self.tasks._require_user(user_id, write=True)
        current = self.session(user_id, session_id)
        require_task_version(current.version, expected_version)
        if (
            current.starts_at <= self.tasks.now()
            or current.cancelled
            or (pinned is not None and type(pinned) is not bool)
        ):
            raise TaskVersionConflict()
        result = replace(
            current,
            version=current.version + 1,
            pinned=current.pinned if pinned is None else pinned,
            cancelled=cancel,
        )
        self.repository.put_session(result)
        return result
