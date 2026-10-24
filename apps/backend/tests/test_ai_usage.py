from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.modules.ai.application.usage import summarize, usage_window
from app.modules.ai.domain.state import InvalidAiState


def test_usage_civil_day_bounds_follow_dst_and_reject_unbounded_ranges() -> None:
    now = datetime(2026, 11, 2, tzinfo=UTC)
    _, _, start, end = usage_window(
        "America/New_York", date(2026, 11, 1), date(2026, 11, 1), 7, now
    )
    assert (end - start).total_seconds() == 25 * 3600
    _, _, start, end = usage_window("America/New_York", date(2026, 3, 8), date(2026, 3, 8), 7, now)
    assert (end - start).total_seconds() == 23 * 3600
    for start_date, end_date in (
        (date(2026, 1, 1), date(2026, 2, 1)),
        (None, date(2026, 1, 1)),
        (date(2027, 1, 1), date(2027, 1, 1)),
    ):
        with pytest.raises(InvalidAiState):
            usage_window("UTC", start_date, end_date, 7, now)


def test_unknown_usage_and_currencies_are_not_zero_or_combined() -> None:
    totals = summarize(
        [
            {"runs": 1},
            {
                "attempts": 1,
                "known_input_tokens": 0,
                "known_output_tokens": 10,
                "unknown_input_attempts": 1,
                "unpriced_attempts": 1,
            },
            {
                "attempts": 1,
                "known_input_tokens": 20,
                "known_output_tokens": 3,
                "currency": "USD",
                "cost": Decimal("0.02"),
            },
            {"attempts": 1, "currency": "EUR", "cost": Decimal("0.01")},
        ]
    )
    assert totals.runs == 1 and totals.attempts == 3
    assert totals.input_tokens is None and totals.known_input_tokens == 20
    assert totals.output_tokens == 13
    assert totals.estimated_costs == {"USD": Decimal("0.02"), "EUR": Decimal("0.01")}
