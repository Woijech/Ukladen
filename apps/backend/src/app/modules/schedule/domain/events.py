from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

MINSK = ZoneInfo("Europe/Minsk")


class UnsupportedSchedule(Exception):
    """The source does not provide enough verified information to expand safely."""


class InvalidScheduleRange(Exception):
    pass


@dataclass(frozen=True)
class OfficialEvent:
    id: UUID
    group_id: int
    kind: Literal["lesson", "exam", "announcement"]
    subgroup: int
    starts_at: datetime
    ends_at: datetime
    subject: str | None
    subject_full_name: str | None
    lesson_type: str | None
    note: str | None
    rooms: tuple[str, ...]
    teacher_ids: tuple[int, ...]
    teacher_names: tuple[str, ...]
    active: bool = True

    def __post_init__(self) -> None:
        if (
            self.starts_at.utcoffset() is None
            or self.ends_at.utcoffset() is None
            or self.ends_at <= self.starts_at
            or self.subgroup < 0
        ):
            raise UnsupportedSchedule("invalid_event")

    @property
    def local_date(self) -> date:
        return self.starts_at.astimezone(MINSK).date()

    @property
    def identity_key(self) -> tuple[object, ...]:
        # A unique same-day lesson keeps its ID when its time, room or teacher changes.
        # ponytail: IIS has no stable lesson ID; date/subject changes need explicit reconciliation.
        return (
            self.kind,
            self.local_date,
            self.subgroup,
            self.subject,
            self.subject_full_name,
            self.lesson_type,
            self.note,
        )

    @property
    def content_key(self) -> tuple[object, ...]:
        return (
            *self.identity_key,
            self.starts_at,
            self.ends_at,
            self.rooms,
            self.teacher_ids,
            self.teacher_names,
        )


def academic_week(day: date) -> int:
    if day.year == 1 and day.month < 9:
        raise UnsupportedSchedule("invalid_academic_year")
    year = day.year if day.month >= 9 else day.year - 1
    september = date(year, 9, 1)
    monday = september - timedelta(days=september.weekday())
    return ((day - monday).days // 7) % 4 + 1


def date_interval(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    if (
        date_from == date.min
        or date_to < date_from
        or (date_to - date_from).days >= 366
        or date_to == date.max
    ):
        raise InvalidScheduleRange()
    return (
        datetime.combine(date_from, datetime.min.time(), MINSK).astimezone(UTC),
        datetime.combine(date_to + timedelta(days=1), datetime.min.time(), MINSK).astimezone(UTC),
    )
