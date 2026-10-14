import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Protocol

from app.core.logging import log_failure
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

logger = logging.getLogger(__name__)


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
        started = perf_counter()
        fields = {"group_id": group_id, "group_number": group_number}
        token = self.store.claim(group_id, group_number, self.clock(), force=force)
        if token is None:
            logger.debug("schedule.sync_skipped", extra=fields)
            return self.store.state(group_id, group_number)
        logger.info("schedule.sync_started", extra=fields)
        event_count = 0
        try:
            snapshot = self.provider.get_group_schedule(group_number)
            if snapshot is not None and (
                snapshot.group is None
                or snapshot.group.id != group_id
                or snapshot.group.name != group_number
            ):
                raise AcademicProfileConflict()
            events = expand_schedule(snapshot) if snapshot else []
            event_count = len(events)
            if not self.store.apply(group_id, token, snapshot, events, self.clock()):
                event_count = 0
                logger.warning("schedule.stale_import_discarded", extra=fields)
        except UnsupportedSchedule as error:
            reason = (
                str(error)
                if str(error)
                in {
                    "missing_group",
                    "split_precedence",
                    "nonlocal_source_time",
                    "invalid_time",
                    "invalid_date",
                    "undated_exception",
                    "invalid_period",
                    "missing_week_numbers",
                    "too_many_events",
                    "unknown_weekday",
                    "invalid_event",
                    "invalid_academic_year",
                }
                else "unverified_rule"
            )
            log_failure(
                logger,
                "schedule.unsupported_rule",
                error,
                level=logging.WARNING,
                group_id=group_id,
                group_number=group_number,
                reason=reason,
            )
            self.store.fail(group_id, token, f"unsupported_{reason}", self.clock())
        except (AcademicProfileConflict, UniversityEntityNotFound) as error:
            log_failure(logger, "schedule.identity_conflict", error, **fields)
            self.store.fail(group_id, token, "identity_conflict", self.clock())
        except AcademicProviderUnavailable as error:
            log_failure(logger, "schedule.source_unavailable", error, **fields)
            self.store.fail(group_id, token, "source_unavailable", self.clock())
        state = self.store.state(group_id, group_number)
        logger.log(
            logging.WARNING if state.status in {"error", "unsupported"} else logging.INFO,
            "schedule.sync_finished",
            extra={
                **fields,
                "state": state.status,
                "error_code": state.error_code,
                "event_count": event_count,
                "duration_ms": round((perf_counter() - started) * 1000, 2),
            },
        )
        return state


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
        selected_count = queued_count = 0
        for group in self.groups.selected_groups():
            selected_count += 1
            state = self.store.state(group.id, group.name)
            wait = timedelta(minutes=2) if state.status == "syncing" else self.interval
            if state.last_attempt_at is None or state.last_attempt_at + wait <= now:
                self.jobs.request_sync(group.id, group.name)
                queued_count += 1
        logger.log(
            logging.INFO if queued_count else logging.DEBUG,
            "schedule.refresh_finished",
            extra={"selected_count": selected_count, "queued_count": queued_count},
        )
