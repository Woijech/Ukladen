from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from typing import Literal, TypedDict
from uuid import UUID
from zoneinfo import ZoneInfo

from app.modules.calendar.domain.legacy import (
    DESCRIPTION_MAX_LENGTH as DESCRIPTION_MAX_LENGTH,
)
from app.modules.calendar.domain.legacy import (
    TITLE_MAX_LENGTH as TITLE_MAX_LENGTH,
)
from app.modules.calendar.domain.legacy import (
    PersonalCalendarEvent as PersonalCalendarEvent,
)
from app.modules.calendar.domain.legacy import (
    apply_event_changes as apply_event_changes,
)
from app.modules.calendar.domain.legacy import (
    new_personal_event as new_personal_event,
)
from app.modules.calendar.domain.legacy import (
    normalize_event_changes as normalize_event_changes,
)
from app.modules.calendar.domain.legacy import (
    normalize_event_data as normalize_event_data,
)


class InvalidCalendarInput(ValueError):
    pass


class CalendarEventNotFound(Exception):
    pass


class CalendarConflict(Exception):
    pass


PERSONAL_FIELDS = {"title", "description", "starts_at", "ends_at", "location", "blocks_time"}
OVERRIDE_FIELDS = {"title", "description", "starts_at", "ends_at", "location", "hidden", "skipped"}


class PersonalValues(TypedDict):
    title: str
    description: str | None
    starts_at: datetime
    ends_at: datetime
    location: str | None
    blocks_time: bool


class OverrideValues(TypedDict):
    title: str | None
    description: str | None
    starts_at: datetime | None
    ends_at: datetime | None
    location: str | None
    hidden: bool
    skipped: bool


def text_value(
    value: object, limit: int, *, required: bool = False, trim: bool = True
) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise InvalidCalendarInput()
    value = value.strip() if trim else value
    if len(value) > limit or "\x00" in value or (required and not value):
        raise InvalidCalendarInput()
    return value


def utc_time(value: object) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise InvalidCalendarInput()
    try:
        return value.astimezone(UTC)
    except ValueError, OverflowError:
        raise InvalidCalendarInput() from None


def interval(start: object, end: object) -> tuple[datetime, datetime]:
    starts_at, ends_at = utc_time(start), utc_time(end)
    if ends_at <= starts_at:
        raise InvalidCalendarInput()
    return starts_at, ends_at


def date_range(date_from: date, date_to: date, timezone: str) -> tuple[datetime, datetime]:
    if (
        date_from == date.min
        or date_to == date.max
        or date_to < date_from
        or (date_to - date_from).days >= 366
    ):
        raise InvalidCalendarInput()
    zone = ZoneInfo(timezone)
    return interval(
        datetime.combine(date_from, datetime.min.time(), zone),
        datetime.combine(date_to + timedelta(days=1), datetime.min.time(), zone),
    )


def personal_values(values: Mapping[str, object]) -> PersonalValues:
    if values.keys() - PERSONAL_FIELDS:
        raise InvalidCalendarInput()
    starts_at, ends_at = interval(values.get("starts_at"), values.get("ends_at"))
    blocks_time = values.get("blocks_time", True)
    if type(blocks_time) is not bool:
        raise InvalidCalendarInput()
    title = text_value(values.get("title"), 200, required=True)
    assert title is not None
    return {
        "title": title,
        "description": text_value(values.get("description"), 10000, trim=False),
        "starts_at": starts_at,
        "ends_at": ends_at,
        "location": text_value(values.get("location"), 500),
        "blocks_time": blocks_time,
    }


def override_values(values: Mapping[str, object]) -> OverrideValues:
    if values.keys() - OVERRIDE_FIELDS:
        raise InvalidCalendarInput()
    start, end = values.get("starts_at"), values.get("ends_at")
    starts_at, ends_at = (
        interval(start, end) if start is not None or end is not None else (None, None)
    )
    hidden, skipped = values.get("hidden", False), values.get("skipped", False)
    if type(hidden) is not bool or type(skipped) is not bool:
        raise InvalidCalendarInput()
    title = values.get("title")
    return {
        "title": text_value(title, 200, required=title is not None),
        "description": text_value(values.get("description"), 10000, trim=False),
        "starts_at": starts_at,
        "ends_at": ends_at,
        "location": text_value(values.get("location"), 500),
        "hidden": hidden,
        "skipped": skipped,
    }


@dataclass(frozen=True, kw_only=True)
class PersonalEvent:
    id: UUID
    user_id: UUID
    title: str
    description: str | None
    starts_at: datetime
    ends_at: datetime
    location: str | None
    blocks_time: bool
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, kw_only=True)
class ScheduleOverride:
    user_id: UUID
    official_event_id: UUID
    hidden: bool
    skipped: bool
    title: str | None
    description: str | None
    starts_at: datetime | None
    ends_at: datetime | None
    location: str | None
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, kw_only=True)
class ResolvedEvent:
    id: str
    source: Literal["official", "personal"]
    source_event_id: UUID
    kind: Literal["lesson", "exam", "announcement", "personal"]
    title: str
    description: str | None
    starts_at: datetime
    ends_at: datetime
    location: str | None
    blocks_time: bool
    hidden: bool = False
    skipped: bool = False
    has_override: bool = False
    version: int = 0
    group_id: int | None = None
    subgroup: int | None = None
    subject: str | None = None
    subject_full_name: str | None = None
    lesson_type: str | None = None
    note: str | None = None
    rooms: tuple[str, ...] = ()
    teacher_ids: tuple[int, ...] = ()
    teacher_names: tuple[str, ...] = ()


def apply_override(event: ResolvedEvent, override: ScheduleOverride) -> ResolvedEvent:
    return replace(
        event,
        title=override.title if override.title is not None else event.title,
        description=override.description if override.description is not None else event.description,
        starts_at=override.starts_at if override.starts_at is not None else event.starts_at,
        ends_at=override.ends_at if override.ends_at is not None else event.ends_at,
        location=override.location if override.location is not None else event.location,
        hidden=override.hidden,
        skipped=override.skipped,
        blocks_time=event.blocks_time and not override.skipped,
        has_override=True,
        version=override.version,
    )


def overlaps(event: ResolvedEvent, starts_at: datetime, ends_at: datetime) -> bool:
    return event.starts_at < ends_at and event.ends_at > starts_at
