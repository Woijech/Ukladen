from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from app.modules.calendar.domain.availability import TimeInterval, free_intervals
from app.modules.tasks.domain.planning import WorkPreferences, WorkSession
from app.modules.tasks.domain.tasks import TaskSummary


@dataclass(frozen=True)
class PlannedSession:
    task_id: UUID
    starts_at: datetime
    ends_at: datetime
    retained_id: UUID | None = None


@dataclass(frozen=True)
class UnplacedWork:
    task_id: UUID
    minutes: int | None
    reason: str


@dataclass(frozen=True)
class WorkPlan:
    sessions: list[PlannedSession]
    unplaced: list[UnplacedWork]


def plan_work(
    tasks: list[TaskSummary],
    dependencies: list[tuple[UUID, UUID]],
    selected: set[UUID],
    windows: list[TimeInterval],
    busy: list[TimeInterval],
    fixed: list[WorkSession],
    movable: list[WorkSession],
    preferences: WorkPreferences,
    now: datetime,
) -> WorkPlan:
    """Greedy, dependency-ordered schedule. Unplaced work is not a proof of infeasibility."""
    by_id = {task.id: task for task in tasks}
    children: dict[UUID, set[UUID]] = {}
    for task in tasks:
        if task.parent_id is not None and task.trashed_at is None:
            children.setdefault(task.parent_id, set()).add(task.id)

    def leaves(identifier: UUID) -> set[UUID]:
        pending_nodes, result = [identifier], set()
        while pending_nodes:
            current = pending_nodes.pop()
            if children.get(current):
                pending_nodes.extend(children[current])
            else:
                result.add(current)
        return result

    chosen = set().union(*(leaves(identifier) for identifier in selected))
    predecessors: dict[UUID, set[UUID]] = {}
    for task_id, predecessor in dependencies:
        if by_id[predecessor].status == "done" and by_id[predecessor].trashed_at is None:
            continue
        for leaf in leaves(task_id):
            predecessors.setdefault(leaf, set()).update(leaves(predecessor))
    break_length = timedelta(minutes=preferences.break_minutes)
    occupied = list(busy)
    for item in fixed:
        occupied.append(TimeInterval(item.starts_at - break_length, item.ends_at + break_length))
    result: list[PlannedSession] = []
    unplaced: list[UnplacedWork] = []
    completed: dict[UUID, datetime] = {
        task.id: now for task in tasks if task.status == "done" and task.trashed_at is None
    }
    pending = set(chosen) - completed.keys()
    priorities = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
    while pending:
        eligible = [
            identifier
            for identifier in pending
            if predecessors.get(identifier, set()) <= completed.keys()
        ]
        if not eligible:
            for identifier in sorted(pending, key=str):
                unplaced.append(
                    UnplacedWork(
                        identifier, by_id[identifier].remaining_minutes, "unresolved_dependencies"
                    )
                )
            break
        identifier = min(
            eligible,
            key=lambda value: (
                by_id[value].deadline_at or datetime.max.replace(tzinfo=now.tzinfo),
                priorities[by_id[value].priority],
                str(value),
            ),
        )
        pending.remove(identifier)
        task = by_id[identifier]
        remaining = task.remaining_minutes
        if task.trashed_at is not None or task.status not in ("todo", "in_progress"):
            unplaced.append(UnplacedWork(identifier, remaining, "inactive_task"))
            continue
        if remaining is None:
            unplaced.append(UnplacedWork(identifier, None, "remaining_work_required"))
            continue
        earliest = max([now, *(completed[p] for p in predecessors.get(identifier, set()))])
        task_fixed = [item for item in fixed if item.task_id == identifier and not item.cancelled]
        if any(item.starts_at <= now < item.ends_at for item in task_fixed):
            unplaced.append(UnplacedWork(identifier, remaining, "session_in_progress"))
            continue
        future = [item for item in task_fixed if item.starts_at > now]
        reserved = sum(
            int((item.ends_at - item.starts_at).total_seconds() // 60) for item in future
        )
        if reserved > remaining or any(
            item.starts_at < earliest
            or (task.deadline_at is not None and item.ends_at > task.deadline_at)
            for item in future
        ):
            unplaced.append(
                UnplacedWork(identifier, remaining, "protected_sessions_require_review")
            )
            continue
        remaining -= reserved
        finishes = [earliest, *(item.ends_at for item in future)]
        allowed = []
        for window in windows:
            start = max(window.starts_at, earliest)
            end = min(window.ends_at, task.deadline_at) if task.deadline_at else window.ends_at
            if start < end:
                allowed.append(TimeInterval(start, end))
        for old in sorted(
            (item for item in movable if item.task_id == identifier),
            key=lambda item: item.starts_at,
        ):
            minutes = int((old.ends_at - old.starts_at).total_seconds() // 60)
            free = free_intervals(allowed, occupied, 1)
            if minutes <= remaining and any(
                item.starts_at <= old.starts_at and item.ends_at >= old.ends_at for item in free
            ):
                result.append(PlannedSession(identifier, old.starts_at, old.ends_at, old.id))
                occupied.append(
                    TimeInterval(old.starts_at - break_length, old.ends_at + break_length)
                )
                remaining -= minutes
                finishes.append(old.ends_at)
        while remaining and len(result) < 512:
            slots = free_intervals(allowed, occupied, min(15, remaining))
            if not slots:
                break
            slot = slots[0]
            available = int((slot.ends_at - slot.starts_at).total_seconds() // 60)
            minutes = min(preferences.session_minutes, remaining, available)
            end = slot.starts_at + timedelta(minutes=minutes)
            result.append(PlannedSession(identifier, slot.starts_at, end))
            occupied.append(TimeInterval(slot.starts_at - break_length, end + break_length))
            finishes.append(end)
            remaining -= minutes
        if remaining:
            unplaced.append(UnplacedWork(identifier, remaining, "not_placed_in_allowed_windows"))
        else:
            completed[identifier] = max(finishes)
    return WorkPlan(sorted(result, key=lambda item: (item.starts_at, str(item.task_id))), unplaced)
