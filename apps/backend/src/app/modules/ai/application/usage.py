from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from app.modules.ai.domain.state import InvalidAiState


class UsageMetrics(BaseModel):
    runs: int = 0
    attempts: int = 0
    input_tokens: int | None = 0
    output_tokens: int | None = 0
    known_input_tokens: int = 0
    known_output_tokens: int = 0
    unknown_input_attempts: int = 0
    unknown_output_attempts: int = 0
    unpriced_attempts: int = 0
    unpriced_web_searches: int = 0
    estimated_costs: dict[str, Decimal] = Field(default_factory=dict)


class UsageGroup(UsageMetrics):
    label: str
    fake: bool = False


class UsageReport(BaseModel):
    timezone: str
    date_from: date
    date_to: date
    summary: UsageMetrics
    fake: UsageMetrics
    daily: list[UsageGroup]
    models: list[UsageGroup]
    recent_runs: list[dict[str, Any]]
    limit: int
    offset: int
    has_more: bool
    retained_from: datetime
    retention_partial: bool = False
    index_state: str = "lexical_only_semantic_index_not_implemented"


def usage_window(
    timezone: str,
    date_from: date | None,
    date_to: date | None,
    days: int,
    now: datetime,
) -> tuple[date, date, datetime, datetime]:
    zone = ZoneInfo(timezone)
    today = now.astimezone(zone).date()
    if days not in (7, 30) or (date_from is None) != (date_to is None):
        raise InvalidAiState("Supply both usage dates or a 7/30-day preset.")
    end = date_to or today
    start = date_from or end - timedelta(days=days - 1)
    if not 1 <= (end - start).days + 1 <= 31 or end > today:
        raise InvalidAiState("Usage is limited to 31 civil days through today.")
    return (
        start,
        end,
        datetime.combine(start, time.min, zone).astimezone(UTC),
        datetime.combine(end + timedelta(days=1), time.min, zone).astimezone(UTC),
    )


def summarize(rows: list[dict[str, Any]]) -> UsageMetrics:
    result = UsageMetrics()
    for row in rows:
        for name in (
            "runs",
            "attempts",
            "known_input_tokens",
            "known_output_tokens",
            "unknown_input_attempts",
            "unknown_output_attempts",
            "unpriced_attempts",
            "unpriced_web_searches",
        ):
            setattr(result, name, getattr(result, name) + int(row.get(name) or 0))
        if row.get("currency") and row.get("cost") is not None:
            currency = row["currency"]
            result.estimated_costs[currency] = (
                result.estimated_costs.get(currency, Decimal(0)) + row["cost"]
            )
    result.input_tokens = None if result.unknown_input_attempts else result.known_input_tokens
    result.output_tokens = None if result.unknown_output_attempts else result.known_output_tokens
    return result


def usage_groups(rows: list[dict[str, Any]], key: str) -> list[UsageGroup]:
    groups: dict[tuple[str, bool], list[dict[str, Any]]] = {}
    for row in rows:
        fake = row["provider"] == "fake"
        label = (
            str(row["day"])
            if key == "day"
            else f"{row['provider']} / {row['model']} · {row['credential_source']}"
        )
        groups.setdefault((label, fake), []).append(row)
    return [
        UsageGroup(label=label, fake=fake, **summarize(items).model_dump())
        for (label, fake), items in sorted(groups.items())
    ]


def daily_series(rows: list[dict[str, Any]], start: date, end: date) -> list[UsageGroup]:
    groups = usage_groups(rows, "day")
    present = {item.label for item in groups if not item.fake}
    day = start
    while day <= end:
        if day.isoformat() not in present:
            groups.append(UsageGroup(label=day.isoformat()))
        day += timedelta(days=1)
    return sorted(groups, key=lambda item: (item.label, item.fake))
