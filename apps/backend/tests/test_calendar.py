from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.calendar.application.ports import CalendarRepository
from app.modules.calendar.application.service import CalendarService
from app.modules.calendar.domain.events import (
    InvalidCalendarInput,
    ResolvedEvent,
    ScheduleOverride,
    apply_override,
    date_range,
    override_values,
    personal_values,
)
from app.modules.calendar.presentation.schemas import PersonalEventCreate, PersonalEventPatch
from app.modules.schedule.application.queries import ScheduleEvents, ScheduleQueryService
from app.modules.schedule.application.storage import ScheduleState
from app.modules.schedule.domain.events import OfficialEvent
from app.modules.users.domain.profile import ProfileUnavailable

NOW = datetime(2026, 10, 7, 9, tzinfo=UTC)


def test_local_date_boundaries_use_actual_day_length() -> None:
    start, end = date_range(date(2026, 3, 8), date(2026, 3, 8), "America/New_York")
    assert start == datetime(2026, 3, 8, 5, tzinfo=UTC)
    assert end - start == timedelta(hours=23)
    start, end = date_range(date(2026, 11, 1), date(2026, 11, 1), "America/New_York")
    assert end - start == timedelta(hours=25)
    start, end = date_range(date(2026, 10, 7), date(2026, 10, 7), "Europe/Minsk")
    assert start == datetime(2026, 10, 6, 21, tzinfo=UTC)
    assert end == datetime(2026, 10, 7, 21, tzinfo=UTC)


@pytest.mark.parametrize(
    "start,end",
    [
        (date.min, date.min),
        (date.max, date.max),
        (date(2026, 10, 8), date(2026, 10, 7)),
        (date(2026, 1, 1), date(2027, 1, 2)),
    ],
)
def test_invalid_calendar_ranges(start: date, end: date) -> None:
    with pytest.raises(InvalidCalendarInput):
        date_range(start, end, "UTC")


@pytest.mark.parametrize(
    "changes",
    [
        {"title": " "},
        {"title": None},
        {"title": 123},
        {"title": "a" * 201},
        {"starts_at": NOW.replace(tzinfo=None)},
        {"ends_at": NOW},
        {"blocks_time": "false"},
        {"user_id": uuid4()},
    ],
)
def test_domain_rejects_invalid_personal_values(changes: dict) -> None:
    with pytest.raises(InvalidCalendarInput):
        personal_values(
            {"title": "Study", "starts_at": NOW, "ends_at": NOW + timedelta(hours=1)} | changes
        )


def test_hidden_and_skipped_are_independent_and_announcements_never_block() -> None:
    event = ResolvedEvent(
        id="official:test",
        source="official",
        source_event_id=uuid4(),
        kind="lesson",
        title="OOP",
        description=None,
        starts_at=NOW,
        ends_at=NOW + timedelta(hours=1),
        location="Room",
        blocks_time=True,
    )
    override = ScheduleOverride(
        user_id=uuid4(),
        official_event_id=event.source_event_id,
        version=1,
        created_at=NOW,
        updated_at=NOW,
        **override_values({"hidden": True}),
    )
    hidden = apply_override(event, override)
    assert hidden.hidden and hidden.blocks_time and not hidden.skipped
    skipped = apply_override(event, replace(override, hidden=False, skipped=True))
    assert not skipped.hidden and skipped.skipped and not skipped.blocks_time
    announcement = replace(event, kind="announcement", blocks_time=False)
    assert not apply_override(announcement, replace(override, hidden=False)).blocks_time
    assert event.title == "OOP" and event.blocks_time


def test_transport_rejects_epoch_naive_dates_null_fields_and_empty_patch() -> None:
    valid = {
        "title": "Study",
        "starts_at": NOW.isoformat(),
        "ends_at": (NOW + timedelta(hours=1)).isoformat(),
    }
    for invalid in ({"starts_at": 123}, {"starts_at": "123"}, {"starts_at": "2026-10-07T09:00:00"}):
        with pytest.raises(ValidationError):
            PersonalEventCreate.model_validate(valid | invalid)
    for invalid in ({}, {"starts_at": None}, {"title": None}, {"blocks_time": None}):
        with pytest.raises(ValidationError):
            PersonalEventPatch.model_validate({"expected_version": 1} | invalid)


def test_resolver_fetches_moved_occurrences_and_filters_after_overrides() -> None:
    repository = Mock(spec=CalendarRepository)
    profiles, academics = Mock(), Mock()
    profiles.get_active.return_value.timezone = "UTC"
    selected = academics.get.return_value
    selected.group.id = 42
    schedule = Mock(spec=ScheduleQueryService)
    original = OfficialEvent(
        id=uuid4(),
        group_id=42,
        kind="lesson",
        subgroup=1,
        starts_at=NOW - timedelta(days=1),
        ends_at=NOW - timedelta(days=1) + timedelta(hours=1),
        subject="OOP",
        subject_full_name=None,
        lesson_type="Lecture",
        note=None,
        rooms=(),
        teacher_ids=(),
        teacher_names=(),
    )
    moved = ScheduleOverride(
        user_id=uuid4(),
        official_event_id=original.id,
        version=1,
        created_at=NOW,
        updated_at=NOW,
        **override_values({"starts_at": NOW, "ends_at": NOW + timedelta(hours=1)}),
    )
    schedule.for_interval.return_value = ScheduleEvents(
        [original], ScheduleState(42, "Group", "error", last_success_at=NOW - timedelta(hours=2))
    )
    repository.moved_overrides.return_value = [moved]
    repository.overrides_for_events.return_value = [moved]
    repository.personal_events.return_value = []
    service = CalendarService(repository, profiles, academics, schedule, now=lambda: NOW)
    result = service.get_calendar(moved.user_id, NOW.date(), NOW.date())
    assert len(result.events) == 1 and result.events[0].starts_at == NOW
    assert result.warnings == ["schedule_error", "schedule_stale"]
    assert schedule.for_interval.call_args.args[-1] == (original.id,)
    repository.overrides_for_events.return_value = [
        replace(moved, starts_at=NOW + timedelta(days=1), ends_at=NOW + timedelta(days=1, hours=1))
    ]
    assert service.get_calendar(moved.user_id, NOW.date(), NOW.date()).events == []


def test_calendar_rechecks_canonical_user_before_writes() -> None:
    repository, profiles = Mock(spec=CalendarRepository), Mock()
    profiles.lock_active.return_value = None
    service = CalendarService(repository, profiles, Mock(), Mock())
    with pytest.raises(ProfileUnavailable):
        service.create_personal_event(uuid4(), {})
    repository.create_personal.assert_not_called()
