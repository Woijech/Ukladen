import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from app.modules.calendar.application.service import CalendarService
from app.modules.calendar.application.work_sessions import WorkSessionBusy, WorkSessionQuery
from app.modules.calendar.domain.availability import TimeInterval, free_intervals, merge_intervals
from app.modules.calendar.domain.events import InvalidCalendarInput, ResolvedEvent
from app.modules.schedule.application.storage import ScheduleState


@dataclass(frozen=True)
class CalendarConflictEntry:
    candidate_index: int
    event_ids: list[str]


@dataclass(frozen=True)
class CalendarAvailability:
    occupied: list[TimeInterval]
    free: list[TimeInterval]
    events: list[ResolvedEvent | WorkSessionBusy]
    conflicts: list[CalendarConflictEntry]
    timezone: str
    source: ScheduleState | None
    warnings: list[str]
    verified: bool
    snapshot: str


class CalendarAvailabilityService:
    def __init__(
        self, calendar: CalendarService, work_sessions: WorkSessionQuery | None = None
    ) -> None:
        self.calendar, self.work_sessions = calendar, work_sessions

    def read(
        self,
        user_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
        windows: list[TimeInterval],
        *,
        minimum_minutes: int = 15,
        candidates: list[TimeInterval] | None = None,
        exclude_personal_event_id: UUID | None = None,
        exclude_work_session_ids: frozenset[UUID] = frozenset(),
    ) -> CalendarAvailability:
        requested = TimeInterval(starts_at, ends_at)
        candidates = candidates if candidates is not None else []
        if (
            requested.ends_at - requested.starts_at > timedelta(days=366)
            or len(windows) > 1024
            or len(candidates) > 1024
            or any(
                item.starts_at < requested.starts_at or item.ends_at > requested.ends_at
                for item in [*windows, *candidates]
            )
        ):
            raise InvalidCalendarInput()
        profile = self.calendar._profile(user_id)
        if exclude_personal_event_id is not None:
            self.calendar.get_personal_event(user_id, exclude_personal_event_id)
        zone = ZoneInfo(profile.timezone)
        result = self.calendar.get_calendar(
            user_id,
            requested.starts_at.astimezone(zone).date(),
            (requested.ends_at - timedelta(microseconds=1)).astimezone(zone).date(),
            include_hidden=True,
        )
        events: list[ResolvedEvent | WorkSessionBusy] = [
            item
            for item in result.events
            if item.blocks_time
            and item.starts_at < requested.ends_at
            and item.ends_at > requested.starts_at
            and not (
                item.source == "personal" and item.source_event_id == exclude_personal_event_id
            )
        ]
        if self.work_sessions is not None:
            events.extend(
                item
                for item in self.work_sessions.busy(user_id, requested.starts_at, requested.ends_at)
                if item.source_event_id not in exclude_work_session_ids
            )
        intervals = [
            TimeInterval(
                max(item.starts_at, requested.starts_at), min(item.ends_at, requested.ends_at)
            )
            for item in events
        ]
        free = free_intervals(windows, intervals, minimum_minutes)
        conflicts = [
            CalendarConflictEntry(
                index,
                [
                    item.id
                    for item in events
                    if item.starts_at < candidate.ends_at and item.ends_at > candidate.starts_at
                ],
            )
            for index, candidate in enumerate(candidates)
        ]
        warnings = list(result.warnings)
        if result.source is not None:
            # Source status/term boundaries do not establish complete IIS coverage.
            warnings.append("schedule_coverage_unknown")
        snapshot = hashlib.sha256(
            json.dumps(
                {
                    "timezone": result.timezone,
                    "source": asdict(result.source) if result.source else None,
                    "events": [asdict(item) for item in events],
                    "warnings": warnings,
                    "starts_at": requested.starts_at,
                    "ends_at": requested.ends_at,
                },
                sort_keys=True,
                default=str,
            ).encode()
        ).hexdigest()
        return CalendarAvailability(
            merge_intervals(intervals),
            free,
            events,
            conflicts,
            result.timezone,
            result.source,
            warnings,
            result.source is None,
            snapshot,
        )
