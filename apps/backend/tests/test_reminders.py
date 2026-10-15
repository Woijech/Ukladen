from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.modules.reminders.domain.reminders import InvalidReminderInput, trigger_time


def test_trigger_uses_elapsed_utc_minutes_across_dst() -> None:
    start = datetime(2026, 10, 25, 2, 30, tzinfo=ZoneInfo("Europe/Berlin"), fold=1)
    assert trigger_time(start, 60, datetime(2026, 10, 24, tzinfo=UTC)) == datetime(
        2026, 10, 25, 0, 30, tzinfo=UTC
    )


@pytest.mark.parametrize("minutes", [-1, 43201, True, 1.5])
def test_trigger_rejects_invalid_offsets(minutes) -> None:
    now = datetime.now(UTC)
    with pytest.raises(InvalidReminderInput):
        trigger_time(now + timedelta(days=40), minutes, now)


def test_trigger_rejects_naive_past_and_underflow_times() -> None:
    now = datetime.now(UTC)
    for start, minutes in (
        (now, 0),
        (now.replace(tzinfo=None), 0),
        (datetime.min.replace(tzinfo=UTC), 1),
    ):
        with pytest.raises(InvalidReminderInput):
            trigger_time(start, minutes, now)
