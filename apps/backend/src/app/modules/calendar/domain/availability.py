from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import islice

from app.modules.calendar.domain.events import InvalidCalendarInput, interval


@dataclass(frozen=True, order=True)
class TimeInterval:
    starts_at: datetime
    ends_at: datetime

    def __post_init__(self) -> None:
        start, end = interval(self.starts_at, self.ends_at)
        object.__setattr__(self, "starts_at", start)
        object.__setattr__(self, "ends_at", end)


def merge_intervals(values: Iterable[TimeInterval]) -> list[TimeInterval]:
    merged: list[TimeInterval] = []
    for item in sorted(values):
        if merged and item.starts_at <= merged[-1].ends_at:
            merged[-1] = TimeInterval(merged[-1].starts_at, max(merged[-1].ends_at, item.ends_at))
        else:
            merged.append(item)
    return merged


def free_intervals(
    windows: Iterable[TimeInterval], busy: Iterable[TimeInterval], minimum_minutes: int = 1
) -> list[TimeInterval]:
    if type(minimum_minutes) is not int or not 1 <= minimum_minutes <= 525600:
        raise InvalidCalendarInput()
    occupied = merge_intervals(busy)
    result: list[TimeInterval] = []
    minimum = timedelta(minutes=minimum_minutes)
    index = 0
    for window in merge_intervals(windows):
        cursor = window.starts_at
        while index < len(occupied) and occupied[index].ends_at <= cursor:
            index += 1
        for item in islice(occupied, index, None):
            if item.starts_at >= window.ends_at:
                break
            end = min(item.starts_at, window.ends_at)
            if end - cursor >= minimum:
                result.append(TimeInterval(cursor, end))
            cursor = max(cursor, item.ends_at)
            if cursor >= window.ends_at:
                break
        if window.ends_at - cursor >= minimum:
            result.append(TimeInterval(cursor, window.ends_at))
    return result
