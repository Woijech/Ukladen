from datetime import UTC, date, datetime

import pytest
from pydantic import TypeAdapter
from test_bsuir_public_api import public_payload

from app.integrations.bsuir.public_api import normalize_payload
from app.modules.schedule.application.expansion import expand_schedule
from app.modules.schedule.application.provider import Schedule
from app.modules.schedule.domain.events import (
    InvalidScheduleRange,
    UnsupportedSchedule,
    academic_week,
    date_interval,
)


def schedule_fixture() -> Schedule:
    data = public_payload("group_schedule")
    lesson = next(iter(data["schedules"].values()))[0]
    lesson.update(
        weekNumber=[1, 3],
        startLessonDate="01.09.2026",
        endLessonDate="30.09.2026",
        startLessonTime="09:00",
        endLessonTime="10:20",
        dateLesson=None,
        split=False,
        announcement=False,
    )
    data.update(schedules={"Понедельник": [lesson]}, exams=[], nextSchedules=None)
    return TypeAdapter(Schedule).validate_python(normalize_payload(data))


def test_week_cycle_matches_official_calendar_and_rollovers() -> None:
    for day, expected in [
        (date(2026, 9, 1), 1),
        (date(2026, 9, 6), 1),
        (date(2026, 9, 7), 2),
        (date(2026, 9, 28), 1),
        (date(2026, 10, 5), 2),
        (date(2027, 1, 1), 2),
        (date(2027, 2, 1), 3),
        (date(2027, 9, 1), 1),
    ]:
        assert academic_week(day) == expected


def test_recurrence_dates_timezone_and_duplicate_elimination() -> None:
    schedule = schedule_fixture()
    events = expand_schedule(schedule)
    assert [event.local_date for event in events] == [date(2026, 9, 14), date(2026, 9, 28)]
    assert events[0].starts_at == datetime(2026, 9, 14, 6, tzinfo=UTC)
    assert schedule.schedules
    duplicate = schedule.model_copy(
        update={
            "schedules": {
                "Понедельник": schedule.schedules["Понедельник"] * 2,
            }
        }
    )
    assert len(expand_schedule(duplicate)) == 2


def test_dated_exams_next_period_and_announcements_are_preserved() -> None:
    schedule = schedule_fixture()
    assert schedule.schedules
    lesson = schedule.schedules["Понедельник"][0]
    exam = lesson.model_copy(update={"date": date(2027, 1, 5), "week_numbers": []})
    notice = exam.model_copy(update={"announcement": True, "subject": None})
    future = lesson.model_copy(
        update={"starts_on": date(2027, 2, 1), "ends_on": date(2027, 2, 1), "week_numbers": [3]}
    )
    schedule = schedule.model_copy(
        update={"exams": [exam, notice], "next_schedules": {"Понедельник": [future]}}
    )
    events = expand_schedule(schedule)
    assert {event.kind for event in events} == {"lesson", "exam", "announcement"}
    assert date(2027, 2, 1) in [event.local_date for event in events]


@pytest.mark.parametrize(
    "patch",
    [
        {"split": True},
        {"announcement": True},
        {"week_numbers": []},
        {"ends_at": datetime.min.time()},
        {"starts_on": date(2028, 1, 1)},
    ],
)
def test_unverified_or_invalid_rules_fail_expansion(patch: dict[str, object]) -> None:
    schedule = schedule_fixture()
    assert schedule.schedules
    lesson = schedule.schedules["Понедельник"][0].model_copy(update=patch)
    with pytest.raises(UnsupportedSchedule):
        expand_schedule(schedule.model_copy(update={"schedules": {"Понедельник": [lesson]}}))


def test_inclusive_bounded_range() -> None:
    start, end = date_interval(date(2026, 10, 5), date(2026, 10, 5))
    assert start == datetime(2026, 10, 4, 21, tzinfo=UTC)
    assert end == datetime(2026, 10, 5, 21, tzinfo=UTC)
    for dates in [
        (date(2026, 2, 1), date(2026, 1, 1)),
        (date(2026, 1, 1), date(2027, 1, 2)),
        (date.max, date.max),
    ]:
        with pytest.raises(InvalidScheduleRange):
            date_interval(*dates)
