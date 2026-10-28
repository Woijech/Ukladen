from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.modules.tasks.domain.tasks import (
    InvalidTaskInput,
    TaskVersionConflict,
    require_task_version,
    task_values,
)


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"title": " \t\n"},
        {"title": None},
        {"title": "x" * 201},
        {"description": "x" * 10001},
        {"title": "bad\x00title"},
        {"description": "\ud800"},
        {"status": None},
        {"status": "blocked"},
        {"priority": None},
        {"priority": "highest"},
        {"estimated_minutes": True},
        {"estimated_minutes": 0},
        {"estimated_minutes": 525601},
        {"estimated_minutes": "30"},
        {"estimated_minutes": 1.5},
        {"deadline_at": datetime(2026, 10, 1)},
        {"deadline_at": "2026-10-01T00:00:00Z"},
        {"user_id": "foreign"},
        {"parent_id": "not-a-uuid"},
    ],
)
def test_invalid_task_values(values: dict[str, object]) -> None:
    payload = {"title": "Task"} | values if values else values
    with pytest.raises(InvalidTaskInput):
        task_values(payload)


def test_task_normalization_preserves_description_and_normalizes_deadline() -> None:
    local = datetime(2026, 10, 1, 18, tzinfo=timezone(timedelta(hours=3)))
    result = task_values({"title": " Study ", "description": " \nNotes ", "deadline_at": local})
    assert result == {
        "title": "Study",
        "description": " \nNotes ",
        "status": "todo",
        "priority": "normal",
        "deadline_at": datetime(2026, 10, 1, 15, tzinfo=UTC),
        "estimated_minutes": None,
        "parent_id": None,
    }
    parent = uuid4()
    assert task_values({"title": "Child", "parent_id": parent})["parent_id"] == parent
    assert (
        task_values({"title": "Task", "estimated_minutes": 525600})["estimated_minutes"] == 525600
    )


@pytest.mark.parametrize("expected", [True, 0, -1, 2**31 - 1, "1"])
def test_invalid_expected_version(expected: object) -> None:
    with pytest.raises(InvalidTaskInput):
        require_task_version(1, expected)  # type: ignore[arg-type]


def test_stale_version_is_distinct_from_invalid_input() -> None:
    with pytest.raises(TaskVersionConflict):
        require_task_version(2, 1)
