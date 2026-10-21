from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import create_autospec
from uuid import uuid4

import pytest

from app.modules.tasks.application.ports import TaskRepository
from app.modules.tasks.application.service import TaskService
from app.modules.tasks.domain.tasks import InvalidTaskInput, TaskNotFound, TaskVersionConflict
from app.modules.users.application.ports import UserAuthentication
from app.modules.users.domain.profile import ProfileUnavailable

NOW = datetime(2026, 10, 21, 12, tzinfo=UTC)


def setup_service():
    repository = create_autospec(TaskRepository, instance=True)
    users = create_autospec(UserAuthentication, instance=True)
    users.is_active.return_value = users.lock_active.return_value = True
    return TaskService(repository, users, now=lambda: NOW), repository, users


def test_create_and_partial_update_preserve_independent_state() -> None:
    service, repository, users = setup_service()
    owner = uuid4()
    task = service.create(
        owner,
        {
            "title": " Task ",
            "description": "Private",
            "estimated_minutes": 90,
            "deadline_at": NOW - timedelta(days=1),
        },
    )
    assert task.title == "Task" and task.status == "todo" and task.version == 1
    assert task.is_overdue(NOW) and task.user_id == owner
    users.lock_active.assert_called_once_with(owner)
    repository.create.assert_called_once_with(task)
    repository.get.return_value = task
    changed = service.update(owner, task.id, {"description": None}, 1)
    assert changed.version == 2 and changed.description is None
    assert changed.estimated_minutes == 90 and changed.deadline_at == task.deadline_at
    assert changed.created_at == task.created_at and changed.id == task.id
    repository.save.assert_called_once_with(changed, 1)
    repository.get.return_value = changed
    cleared = service.update(owner, task.id, {"estimated_minutes": None, "deadline_at": None}, 2)
    assert cleared.deadline_at is None and cleared.estimated_minutes is None
    assert not cleared.is_overdue(NOW)


@pytest.mark.parametrize("status", ["todo", "in_progress", "done", "cancelled"])
def test_explicit_transitions_and_deadline_boundary(status) -> None:
    service, repository, _ = setup_service()
    task = service.create(uuid4(), {"title": "Task", "status": "done", "deadline_at": NOW})
    assert not task.is_overdue(NOW)
    repository.get.return_value = task
    changed = service.update(task.user_id, task.id, {"status": status}, 1)
    assert changed.status == status
    assert changed.is_overdue(NOW + timedelta(seconds=1)) == (status in ("todo", "in_progress"))


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"title": None},
        {"status": None},
        {"priority": None},
        {"id": uuid4()},
        {"user_id": uuid4()},
        {"version": 2},
    ],
)
def test_invalid_updates_never_write(changes) -> None:
    service, repository, _ = setup_service()
    task = service.create(uuid4(), {"title": "Task"})
    repository.get.return_value = task
    with pytest.raises(InvalidTaskInput):
        service.update(task.user_id, task.id, changes, 1)
    repository.save.assert_not_called()


def test_stale_update_and_missing_task() -> None:
    service, repository, _ = setup_service()
    task = service.create(uuid4(), {"title": "Task"})
    repository.get.return_value = replace(task, version=2)
    with pytest.raises(TaskVersionConflict):
        service.update(task.user_id, task.id, {"title": "Overwrite"}, 1)
    repository.save.assert_not_called()
    repository.get.return_value = None
    with pytest.raises(TaskNotFound):
        service.get(task.user_id, task.id)
    with pytest.raises(TaskNotFound):
        service.update(task.user_id, task.id, {"title": "Missing"}, 1)


def test_reads_and_writes_recheck_canonical_user() -> None:
    service, repository, users = setup_service()
    users.is_active.return_value = users.lock_active.return_value = False
    with pytest.raises(ProfileUnavailable):
        service.get(uuid4(), uuid4())
    with pytest.raises(ProfileUnavailable):
        service.list(uuid4())
    with pytest.raises(ProfileUnavailable):
        service.create(uuid4(), {"title": "Denied"})
    with pytest.raises(ProfileUnavailable):
        service.update(uuid4(), uuid4(), {"title": "Denied"}, 1)
    repository.create.assert_not_called()
    repository.get.assert_not_called()
    repository.save.assert_not_called()


@pytest.mark.parametrize(
    "values",
    [
        {"limit": 0},
        {"limit": True},
        {"limit": 201},
        {"offset": -1},
        {"offset": True},
        {"offset": 2**31},
        {"status": "unknown"},
        {"priority": "unknown"},
    ],
)
def test_invalid_lists_rejected(values) -> None:
    service, repository, _ = setup_service()
    with pytest.raises(InvalidTaskInput):
        service.list(uuid4(), **values)
    repository.list.assert_not_called()
