from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import create_autospec
from uuid import uuid4

import pytest

from app.modules.tasks.application.ports import TaskRepository
from app.modules.tasks.application.service import TaskService
from app.modules.tasks.domain.tasks import (
    InvalidTaskInput,
    TaskHierarchyConflict,
    TaskNotFound,
    TaskVersionConflict,
)
from app.modules.users.application.ports import UserAuthentication
from app.modules.users.domain.profile import ProfileUnavailable

NOW = datetime(2026, 10, 21, 12, tzinfo=UTC)


def setup_service():
    repository = create_autospec(TaskRepository, instance=True)
    users = create_autospec(UserAuthentication, instance=True)
    users.is_active.return_value = users.lock_active.return_value = True
    repository.has_open_descendants.return_value = False
    return TaskService(repository, users, now=lambda: NOW), repository, users


def test_subtask_parent_owner_and_cycle_rules() -> None:
    service, repository, _ = setup_service()
    owner = uuid4()
    root = service.create(owner, {"title": "Root"})
    child = service.create(owner, {"title": "Child"})
    grandchild = service.create(owner, {"title": "Grandchild"})
    tasks = {
        root.id: root,
        child.id: replace(child, parent_id=root.id),
        grandchild.id: replace(grandchild, parent_id=child.id),
    }
    repository.get.side_effect = lambda user_id, task_id: (
        tasks.get(task_id) if user_id == owner else None
    )
    with pytest.raises(TaskHierarchyConflict):
        service.update(owner, root.id, {"parent_id": grandchild.id}, 1)
    with pytest.raises(TaskHierarchyConflict):
        service.update(owner, child.id, {"parent_id": child.id}, 1)
    with pytest.raises(TaskNotFound):
        service.create(owner, {"title": "Private", "parent_id": uuid4()})
    with pytest.raises(TaskNotFound):
        service.update(owner, child.id, {"parent_id": uuid4()}, 1)
    repository.save.assert_not_called()


def test_deep_parent_chain_has_no_fixed_depth_limit() -> None:
    service, repository, _ = setup_service()
    owner = uuid4()
    root = service.create(owner, {"title": "Root"})
    tasks = {root.id: root}
    parent_id = root.id
    for _ in range(1100):
        child = replace(root, id=uuid4(), parent_id=parent_id)
        tasks[child.id] = child
        parent_id = child.id
    repository.get.side_effect = lambda _, task_id: tasks.get(task_id)
    created = service.create(owner, {"title": "Deep child", "parent_id": parent_id})
    assert created.parent_id == parent_id


def test_completion_and_reopening_enforce_descendant_state() -> None:
    service, repository, _ = setup_service()
    owner = uuid4()
    root = service.create(owner, {"title": "Root"})
    child = replace(service.create(owner, {"title": "Child"}), parent_id=root.id)
    repository.get.side_effect = lambda _, task_id: {root.id: root, child.id: child}.get(task_id)
    repository.has_open_descendants.return_value = True
    with pytest.raises(TaskHierarchyConflict):
        service.update(owner, root.id, {"status": "done"}, 1)
    repository.has_open_descendants.return_value = False
    done = service.update(owner, root.id, {"status": "done"}, 1)
    repository.get.side_effect = lambda _, task_id: {root.id: done, child.id: child}.get(task_id)
    with pytest.raises(TaskHierarchyConflict):
        service.create(owner, {"title": "New open child", "parent_id": root.id})
    with pytest.raises(TaskHierarchyConflict):
        service.update(owner, child.id, {"status": "todo"}, 1)


def test_combined_parent_and_status_patch_checks_final_state() -> None:
    service, repository, _ = setup_service()
    owner = uuid4()
    done = service.create(owner, {"title": "Done", "status": "done"})
    child = service.create(owner, {"title": "Child", "status": "done"})
    repository.get.side_effect = lambda _, task_id: {done.id: done, child.id: child}.get(task_id)
    with pytest.raises(TaskHierarchyConflict):
        service.update(owner, child.id, {"parent_id": done.id, "status": "todo"}, 1)
    repository.has_open_descendants.return_value = True
    with pytest.raises(TaskHierarchyConflict):
        service.update(owner, child.id, {"parent_id": done.id, "status": "cancelled"}, 1)
    repository.has_open_descendants.return_value = False
    moved = service.update(owner, child.id, {"parent_id": done.id, "status": "cancelled"}, 1)
    assert moved.parent_id == done.id and moved.status == "cancelled"


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
        {"parent_id": "invalid"},
        {"roots_only": 1},
        {"parent_id": uuid4(), "roots_only": True},
    ],
)
def test_invalid_lists_rejected(values) -> None:
    service, repository, _ = setup_service()
    with pytest.raises(InvalidTaskInput):
        service.list(uuid4(), **values)
    repository.list.assert_not_called()
