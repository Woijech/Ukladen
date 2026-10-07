from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from app.modules.academics.application.directory import UniversityEntityNotFound
from app.modules.academics.application.ports import (
    AcademicProviderUnavailable,
    SelectedGroupDirectory,
)
from app.modules.academics.domain.profile import AcademicProfileConflict
from app.modules.schedule.application.expansion import expand_schedule
from app.modules.schedule.application.provider import ScheduleProvider
from app.modules.schedule.application.storage import ScheduleState, ScheduleStore
from app.modules.schedule.domain.events import UnsupportedSchedule


class ScheduleSyncUnavailable(Exception):
    pass


class ScheduleJobs(Protocol):
    def request_sync(self, group_id: int, group_number: str, *, force: bool = False) -> None: ...


def utc_now() -> datetime:
    return datetime.now(UTC)


class ScheduleSyncService:
    def __init__(
        self,
        provider: ScheduleProvider,
        store: ScheduleStore,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.provider, self.store, self.clock = provider, store, clock

    def sync(self, group_id: int, group_number: str, *, force: bool = False) -> ScheduleState:
        token = self.store.claim(group_id, group_number, self.clock(), force=force)
        if token is None:
            return self.store.state(group_id, group_number)
        try:
            snapshot = self.provider.get_group_schedule(group_number)
            if snapshot is not None and (
                snapshot.group is None
                or snapshot.group.id != group_id
                or snapshot.group.name != group_number
            ):
                raise AcademicProfileConflict()
            events = expand_schedule(snapshot) if snapshot else []
            self.store.apply(group_id, token, snapshot, events, self.clock())
        except UnsupportedSchedule:
            self.store.fail(group_id, token, "unsupported_schedule", self.clock())
        except AcademicProfileConflict, UniversityEntityNotFound:
            self.store.fail(group_id, token, "identity_conflict", self.clock())
        except AcademicProviderUnavailable:
            self.store.fail(group_id, token, "source_unavailable", self.clock())
        return self.store.state(group_id, group_number)


class ScheduleRefreshService:
    def __init__(
        self,
        groups: SelectedGroupDirectory,
        store: ScheduleStore,
        jobs: ScheduleJobs,
        interval_seconds: int,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.groups, self.store, self.jobs = groups, store, jobs
        self.interval = timedelta(seconds=interval_seconds)
        self.clock = clock

    def refresh(self) -> None:
        now = self.clock()
        for group in self.groups.selected_groups():
            state = self.store.state(group.id, group.name)
            wait = timedelta(minutes=2) if state.status == "syncing" else self.interval
            if state.last_attempt_at is None or state.last_attempt_at + wait <= now:
                self.jobs.request_sync(group.id, group.name)
