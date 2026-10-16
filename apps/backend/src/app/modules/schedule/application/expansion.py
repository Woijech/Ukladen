from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from app.modules.schedule.application.provider import Lesson, Schedule
from app.modules.schedule.domain.events import (
    MINSK,
    OfficialEvent,
    UnsupportedSchedule,
    academic_week,
)

WEEKDAYS = {
    "Понедельник": 0,
    "Вторник": 1,
    "Среда": 2,
    "Четверг": 3,
    "Пятница": 4,
    "Суббота": 5,
    "Воскресенье": 6,
}
MAX_EVENTS = 20_000


def expand_schedule(schedule: Schedule) -> list[OfficialEvent]:
    if schedule.group is None:
        raise UnsupportedSchedule("missing_group")
    group_id = schedule.group.id
    events: dict[tuple[object, ...], OfficialEvent] = {}

    def expand(
        lesson: Lesson, weekday: int | None, *, next_period: bool = False, exam: bool = False
    ) -> None:
        # IIS renders split rows using the same explicit dates, weeks and subgroup.
        if lesson.starts_at.tzinfo is not None or lesson.ends_at.tzinfo is not None:
            raise UnsupportedSchedule("nonlocal_source_time")
        if lesson.ends_at <= lesson.starts_at:
            raise UnsupportedSchedule("invalid_time")
        if lesson.date is not None:
            if lesson.date in (date.min, date.max):
                raise UnsupportedSchedule("invalid_date")
            days = [lesson.date]
        else:
            if weekday is None or lesson.announcement:
                raise UnsupportedSchedule("undated_exception")
            start = lesson.starts_on or (None if next_period else schedule.starts_on)
            end = lesson.ends_on or (None if next_period else schedule.ends_on)
            if (
                start is None
                or end is None
                or end == date.max
                or start > end
                or (end - start).days >= 366
            ):
                raise UnsupportedSchedule("invalid_period")
            if not lesson.week_numbers:
                raise UnsupportedSchedule("missing_week_numbers")
            offset = (weekday - start.weekday()) % 7
            if (end - start).days < offset:
                return
            day = start + timedelta(days=offset)
            days = []
            while day <= end:
                if academic_week(day) in lesson.week_numbers:
                    days.append(day)
                if (end - day).days < 7:
                    break
                day += timedelta(days=7)
        for day in days:
            teachers = sorted(lesson.teachers or [], key=lambda teacher: teacher.id)
            event = OfficialEvent(
                id=uuid4(),
                group_id=group_id,
                kind="announcement" if lesson.announcement else "exam" if exam else "lesson",
                subgroup=lesson.subgroup,
                starts_at=datetime.combine(day, lesson.starts_at, MINSK).astimezone(UTC),
                ends_at=datetime.combine(day, lesson.ends_at, MINSK).astimezone(UTC),
                subject=lesson.subject,
                subject_full_name=lesson.subject_full_name,
                lesson_type=lesson.lesson_type_abbrev,
                note=lesson.note,
                rooms=tuple(sorted(set(lesson.rooms))),
                teacher_ids=tuple(teacher.id for teacher in teachers),
                teacher_names=tuple(
                    teacher.fio
                    or " ".join(
                        filter(None, (teacher.last_name, teacher.first_name, teacher.middle_name))
                    )
                    for teacher in teachers
                ),
            )
            events[event.content_key] = event
            if len(events) > MAX_EVENTS:
                raise UnsupportedSchedule("too_many_events")

    for next_period, days in [(False, schedule.schedules), (True, schedule.next_schedules)]:
        for weekday, lessons in (days or {}).items():
            if weekday not in WEEKDAYS:
                raise UnsupportedSchedule("unknown_weekday")
            for lesson in lessons:
                expand(lesson, WEEKDAYS[weekday], next_period=next_period)
    for lesson in schedule.exams or []:
        expand(lesson, None, exam=True)
    return sorted(
        events.values(), key=lambda event: (event.starts_at, event.ends_at, event.subgroup)
    )
