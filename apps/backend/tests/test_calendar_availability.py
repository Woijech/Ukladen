from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import create_autospec
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.modules.calendar.application.availability import CalendarAvailabilityService
from app.modules.calendar.application.service import CalendarResult, CalendarService
from app.modules.calendar.domain.availability import TimeInterval, free_intervals, merge_intervals
from app.modules.calendar.domain.events import InvalidCalendarInput, ResolvedEvent
from app.modules.schedule.application.storage import ScheduleState

START = datetime(2026, 10, 28, 9, tzinfo=UTC)


def span(start: int, end: int) -> TimeInterval:
    return TimeInterval(START + timedelta(minutes=start), START + timedelta(minutes=end))


def test_union_merges_nested_overlapping_touching_and_duplicate_intervals() -> None:
    assert merge_intervals(
        [span(60, 90), span(0, 30), span(10, 20), span(30, 60), span(0, 30)]
    ) == [span(0, 90)]
    assert merge_intervals([]) == []


def test_subtraction_clips_busy_edges_and_deduplicates_allowed_windows() -> None:
    windows = [span(0, 180), span(60, 120), span(240, 300)]
    busy = [span(-60, 15), span(30, 60), span(50, 90), span(120, 150), span(270, 330)]
    assert free_intervals(windows, busy, 15) == [
        span(15, 30),
        span(90, 120),
        span(150, 180),
        span(240, 270),
    ]
    assert free_intervals(windows, busy, 30) == [span(90, 120), span(150, 180), span(240, 270)]


def test_touching_busy_events_do_not_overlap_a_window() -> None:
    assert free_intervals([span(0, 60)], [span(-60, 0), span(60, 120)]) == [span(0, 60)]
    assert free_intervals([span(0, 60)], [span(-60, 120)]) == []
    assert free_intervals([], [span(0, 60)]) == []


@pytest.mark.parametrize("minutes", [0, -1, True, 1.5, "15", 525601])
def test_invalid_minimum_duration_is_rejected(minutes) -> None:
    with pytest.raises(InvalidCalendarInput):
        free_intervals([span(0, 60)], [], minutes)


def test_intervals_normalize_offsets_and_dst_fold_before_comparing() -> None:
    zone = ZoneInfo("Europe/Berlin")
    first = datetime(2026, 10, 25, 2, 30, tzinfo=zone, fold=0)
    second = datetime(2026, 10, 25, 2, 30, tzinfo=zone, fold=1)
    window = TimeInterval(first, second)
    assert window.ends_at - window.starts_at == timedelta(hours=1)
    assert window.starts_at.tzinfo == UTC
    assert free_intervals([window], [], 60) == [window]
    with pytest.raises(InvalidCalendarInput):
        TimeInterval(second, first)
    with pytest.raises(InvalidCalendarInput):
        TimeInterval(datetime(2026, 10, 28, 9), START)


def test_calendar_availability_uses_hidden_busy_events_and_marks_unknown_coverage() -> None:
    owner = uuid4()
    calendar = create_autospec(CalendarService, instance=True)
    calendar._profile.return_value.timezone = "Europe/Minsk"
    event = ResolvedEvent(
        id=f"personal:{uuid4()}",
        source="personal",
        source_event_id=uuid4(),
        kind="personal",
        title="Busy",
        description="Private",
        starts_at=START + timedelta(minutes=30),
        ends_at=START + timedelta(minutes=60),
        location=None,
        blocks_time=True,
    )
    calendar.get_calendar.return_value = CalendarResult(
        [
            event,
            replace(
                event,
                id="official:hidden",
                source="official",
                hidden=True,
                starts_at=START + timedelta(minutes=60),
                ends_at=START + timedelta(minutes=90),
            ),
            replace(event, id="personal:nonblocking", blocks_time=False),
        ],
        "Europe/Minsk",
        ScheduleState(1, "Group", status="ready", last_success_at=START),
        [],
    )
    service = CalendarAvailabilityService(calendar)
    result = service.read(
        owner,
        START,
        START + timedelta(hours=2),
        [span(0, 120)],
        candidates=[span(0, 30), span(45, 75)],
    )
    assert result.occupied == [span(30, 90)]
    assert result.free == [span(0, 30), span(90, 120)]
    assert result.conflicts[0].event_ids == []
    assert result.conflicts[1].event_ids == [event.id, "official:hidden"]
    assert not result.verified and "schedule_coverage_unknown" in result.warnings
    assert calendar.get_calendar.call_args.kwargs == {"include_hidden": True}
    same = service.read(owner, START, START + timedelta(hours=2), [span(0, 120)])
    assert result.snapshot == same.snapshot
    calendar.get_calendar.return_value = replace(
        calendar.get_calendar.return_value, source=None, events=[event]
    )
    personal = service.read(owner, START, START + timedelta(hours=2), [span(0, 120)])
    assert personal.verified and personal.snapshot != result.snapshot


def test_availability_exclusions_require_owned_personal_event_and_bounds() -> None:
    calendar = create_autospec(CalendarService, instance=True)
    calendar._profile.return_value.timezone = "UTC"
    event_id, owner = uuid4(), uuid4()
    event = ResolvedEvent(
        id=f"personal:{event_id}",
        source="personal",
        source_event_id=event_id,
        kind="personal",
        title="Editing",
        description=None,
        starts_at=START,
        ends_at=START + timedelta(hours=1),
        location=None,
        blocks_time=True,
    )
    calendar.get_calendar.return_value = CalendarResult([event], "UTC", None, [])
    service = CalendarAvailabilityService(calendar)
    assert service.read(
        owner, START, START + timedelta(hours=1), [span(0, 60)], exclude_personal_event_id=event_id
    ).free == [span(0, 60)]
    calendar.get_personal_event.assert_called_once_with(owner, event_id)
    with pytest.raises(InvalidCalendarInput):
        service.read(owner, START, START + timedelta(hours=1), [span(0, 61)])
