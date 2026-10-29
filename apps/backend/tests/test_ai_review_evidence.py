from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.modules.ai.application.review_evidence import review_facts
from app.modules.calendar.application.availability import CalendarAvailability
from app.modules.calendar.domain.availability import TimeInterval
from app.modules.calendar.domain.events import ResolvedEvent
from app.modules.tasks.domain.planning import WeeklyWindow, WorkPreferences
from app.modules.tasks.domain.tasks import TaskSummary

NOW = datetime(2026, 10, 29, 9, tzinfo=UTC)


def task(**values):
    return replace(
        TaskSummary(
            id=uuid4(),
            user_id=uuid4(),
            title="Calculus",
            status="todo",
            priority="normal",
            deadline_at=NOW + timedelta(hours=2),
            estimated_minutes=100,
            remaining_minutes=100,
            version=1,
            created_at=NOW,
            updated_at=NOW,
        ),
        **values,
    )


def event(start: float = 1, end: float = 2, **values):
    identifier = uuid4()
    return replace(
        ResolvedEvent(
            id=f"personal:{identifier}",
            source="personal",
            source_event_id=identifier,
            kind="personal",
            title="Class",
            starts_at=NOW + timedelta(hours=start),
            ends_at=NOW + timedelta(hours=end),
            blocks_time=True,
            description=None,
            location=None,
        ),
        **values,
    )


def available(events=(), minutes=60):
    return CalendarAvailability(
        [],
        [TimeInterval(NOW, NOW + timedelta(minutes=minutes))],
        list(events),
        [],
        "Europe/Minsk",
        None,
        [],
        True,
        "snapshot",
    )


def test_deadline_boundaries_completed_and_trashed_tasks_and_clock_dedup():
    overdue, soon, boundary = (
        task(deadline_at=NOW - timedelta(seconds=1)),
        task(),
        task(deadline_at=NOW + timedelta(hours=24)),
    )
    values = [
        overdue,
        soon,
        boundary,
        task(status="done"),
        task(status="cancelled"),
        task(trashed_at=NOW),
        task(deadline_at=NOW + timedelta(hours=24, seconds=1)),
    ]
    result = review_facts(values, None, WorkPreferences(), NOW)
    assert [issue["kind"] for issue in result.issues] == ["overdue", "deadline", "deadline"]
    assert (
        result.fingerprint
        == review_facts(
            values, None, WorkPreferences(), NOW + timedelta(microseconds=1)
        ).fingerprint
    )
    assert (
        result.fingerprint
        != review_facts([replace(soon, version=2)], None, WorkPreferences(), NOW).fingerprint
    )


def test_conflicts_ignore_touching_intervals_and_cap_without_losing_event_summary():
    first, second, touching = event(), event(1.5, 2.5), event(2.5, 3)
    result = review_facts([], available([first, second, touching]), WorkPreferences(), NOW)
    assert len(result.issues) == 1 and result.issues[0]["kind"] == "conflict"
    many = review_facts([], available([event() for _ in range(40)]), WorkPreferences(), NOW)
    assert len(many.issues) == 100
    assert len(many.data["events"]) == 40 and "conflicts_partial" in many.warnings


def test_overload_uses_explicit_remaining_without_parent_double_count_or_session_progress():
    parent = task(remaining_minutes=500)
    child = task(parent_id=parent.id, remaining_minutes=45)
    unknown = task(remaining_minutes=None, estimated_minutes=1000)
    preferences = WorkPreferences(1, (WeeklyWindow(3, 540, 1020),))
    result = review_facts([parent, child, unknown], available(), preferences, NOW)
    assert not any(issue["kind"] == "overload" for issue in result.issues)
    assert "remaining_work_unknown" in result.warnings
    result = review_facts(
        [parent, replace(child, remaining_minutes=90)], available(), preferences, NOW
    )
    assert any(issue["kind"] == "overload" for issue in result.issues)
    result = review_facts(
        [child], available(minutes=10), preferences, NOW, capacity=available(minutes=60)
    )
    assert not any(issue["kind"] == "overload" for issue in result.issues)
    assert result.data["sessions_are_not_progress"]


def test_unknown_coverage_is_conditional_and_missing_work_windows_cannot_establish_overload():
    calendar = replace(available(), verified=False, warnings=["schedule_coverage_unknown"])
    prefs = WorkPreferences(1, (WeeklyWindow(3, 540, 1020),))
    result = review_facts([task()], calendar, prefs, NOW, incomplete_tasks=True)
    assert result.issues[-1]["conditional"] is True
    assert "task_scope_partial" in result.warnings
    result = review_facts([task()], calendar, WorkPreferences(), NOW)
    assert not any(issue["kind"] == "overload" for issue in result.issues)
    assert "work_windows_not_configured" in result.warnings


def test_model_input_budget_discloses_truncation_and_cannot_forge_citation_sources():
    import json

    import pytest

    from app.modules.ai.domain.state import AiConflict
    from app.modules.ai.infrastructure.review_generation import REVIEW_POLICY, bounded_briefing

    evidence = review_facts(
        [task(title="Long lecture " * 12) for _ in range(80)], None, WorkPreferences(), NOW
    )
    evidence = replace(evidence, data=evidence.data | {"related_materials": []})
    text, sources = bounded_briefing(evidence, "daily", 6000)
    assert len(text.encode()) + len(REVIEW_POLICY.encode()) + 512 <= 6000
    assert "briefing_evidence_partial" in json.loads(text)["warnings"]
    assert {source.id for source in sources} <= {source.id for source in evidence.sources}
    with pytest.raises(AiConflict):
        bounded_briefing(evidence, "daily", 256)


def test_overload_detects_early_deadline_and_excludes_indirect_parent():
    preferences = WorkPreferences(1, (WeeklyWindow(3, 540, 1020),))
    urgent = task(deadline_at=NOW + timedelta(minutes=30), remaining_minutes=90)
    result = review_facts([urgent], available(minutes=180), preferences, NOW)
    issue = next(issue for issue in result.issues if issue["kind"] == "overload")
    assert urgent.deadline_at is not None
    assert issue["before"] == urgent.deadline_at.isoformat()
    parent = task(remaining_minutes=500)
    grandchild = task(parent_id=uuid4(), remaining_minutes=45)
    result = review_facts(
        [parent, grandchild],
        available(minutes=60),
        preferences,
        NOW,
        excluded_parents=frozenset({parent.id}),
    )
    assert not any(issue["kind"] == "overload" for issue in result.issues)
    assert "parent_effort_excluded" in result.warnings
