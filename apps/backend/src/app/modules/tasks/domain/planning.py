from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from app.modules.calendar.domain.availability import TimeInterval
from app.modules.tasks.domain.tasks import InvalidTaskInput


@dataclass(frozen=True)
class WeeklyWindow:
    weekday: int
    start_minute: int
    end_minute: int

    def __post_init__(self) -> None:
        if any(
            type(v) is not int for v in (self.weekday, self.start_minute, self.end_minute)
        ) or not (0 <= self.weekday <= 6 and 0 <= self.start_minute < self.end_minute <= 1440):
            raise InvalidTaskInput()


@dataclass(frozen=True)
class WorkPreferences:
    version: int = 0
    windows: tuple[WeeklyWindow, ...] = ()
    session_minutes: int = 45
    break_minutes: int = 15

    def __post_init__(self) -> None:
        if (
            len(self.windows) > 28
            or type(self.session_minutes) is not int
            or not 15 <= self.session_minutes <= 240
            or type(self.break_minutes) is not int
            or not 0 <= self.break_minutes <= 120
        ):
            raise InvalidTaskInput()
        ordered = sorted(self.windows, key=lambda w: (w.weekday, w.start_minute))
        if any(
            a.weekday == b.weekday and a.end_minute > b.start_minute
            for a, b in zip(ordered, ordered[1:], strict=False)
        ):
            raise InvalidTaskInput()

    def expand(self, starts_at: datetime, ends_at: datetime, timezone: str) -> list[TimeInterval]:
        requested = TimeInterval(starts_at, ends_at)
        zone = ZoneInfo(timezone)
        day = requested.starts_at.astimezone(zone).date()
        last = requested.ends_at.astimezone(zone).date()
        if (last - day).days > 366:
            raise InvalidTaskInput()
        result = []
        while day <= last:
            for window in self.windows:
                if day.weekday() != window.weekday:
                    continue
                boundaries = []
                for minute in (window.start_minute, window.end_minute):
                    local = datetime.combine(day, time()) + timedelta(minutes=minute)
                    instants = {
                        local.replace(tzinfo=zone, fold=fold).astimezone(UTC)
                        for fold in (0, 1)
                        if local.replace(tzinfo=zone, fold=fold)
                        .astimezone(UTC)
                        .astimezone(zone)
                        .replace(tzinfo=None)
                        == local
                    }
                    if len(instants) != 1:
                        raise InvalidTaskInput(
                            "Ambiguous or nonexistent window boundary; use dated windows."
                        )
                    boundaries.append(instants.pop())
                start, end = (
                    max(boundaries[0], requested.starts_at),
                    min(boundaries[1], requested.ends_at),
                )
                if start < end:
                    result.append(TimeInterval(start, end))
            day += timedelta(days=1)
        return result


@dataclass(frozen=True, kw_only=True)
class WorkSession:
    id: UUID
    user_id: UUID
    task_id: UUID
    starts_at: datetime
    ends_at: datetime
    pinned: bool = False
    cancelled: bool = False
    version: int = 1
