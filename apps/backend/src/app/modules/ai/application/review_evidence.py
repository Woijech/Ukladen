"""Deterministic review facts; a model may explain them but cannot invent findings."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from pydantic import JsonValue

from app.modules.ai.application.sources import json_value
from app.modules.calendar.application.availability import CalendarAvailability
from app.modules.calendar.application.work_sessions import WorkSessionBusy
from app.modules.search.domain.evidence import SourceReference
from app.modules.tasks.domain.planning import WorkPreferences
from app.modules.tasks.domain.tasks import TaskSummary


@dataclass(frozen=True)
class ReviewEvidence:
    data: dict
    sources: tuple[SourceReference, ...]
    issues: tuple[dict, ...]
    warnings: tuple[str, ...]

    @property
    def fingerprint(self) -> str:
        # Clock movement and prose are not a meaningful change to an existing problem.
        return digest(self.issues)

    @property
    def actionable(self) -> bool:
        return bool(self.data.get("tasks") or self.data.get("events") or self.issues)

    def payload(self) -> JsonValue:
        return json_value(
            {
                "facts": self.data,
                "issues": self.issues[:30],
                "warnings": self.warnings,
                "sources": [source.model_dump(mode="json") for source in self.sources],
            }
        )


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def review_facts(
    tasks: list[TaskSummary],
    availability: CalendarAvailability | None,
    preferences: WorkPreferences,
    now: datetime,
    *,
    incomplete_tasks: bool = False,
    capacity: CalendarAvailability | None = None,
    excluded_parents: frozenset[UUID] = frozenset(),
) -> ReviewEvidence:
    ends_at = now + timedelta(days=7)
    active = sorted(
        (
            task
            for task in tasks
            if task.status in ("todo", "in_progress") and task.trashed_at is None
        ),
        key=lambda task: (task.deadline_at or ends_at, str(task.id)),
    )
    active_ids = {task.id for task in active}
    issues: list[dict] = []
    warnings = ["task_scope_partial"] if incomplete_tasks else []
    sources = [
        SourceReference(
            source="task",
            id=str(task.id),
            version=task.version,
            title=task.title,
            locator="task:summary",
        )
        for task in active
    ]
    for task in active:
        if task.deadline_at is not None and task.deadline_at <= now + timedelta(hours=24):
            issues.append(
                {
                    "kind": "overdue" if task.deadline_at < now else "deadline",
                    "task_id": str(task.id),
                    "version": task.version,
                    "deadline_at": task.deadline_at.isoformat(),
                }
            )
    events = []
    free_minutes = None
    conflicts = 0
    if availability is not None:
        warnings.extend(availability.warnings)
        ordered = sorted(availability.events, key=lambda item: (item.starts_at, item.id))
        # shortcut: bound conflict evidence to 500 events; disclose partial coverage above that.
        if len(ordered) > 500:
            warnings.append("calendar_events_partial")
        ordered = ordered[:500]
        for index, event in enumerate(ordered):
            events.append(
                {
                    "id": event.id,
                    "title": event.title,
                    "starts_at": event.starts_at.isoformat(),
                    "ends_at": event.ends_at.isoformat(),
                    "version": event.version,
                }
            )
            if isinstance(event, WorkSessionBusy) and event.task_id in active_ids:
                events[-1]["task_id"] = str(event.task_id)
            if event.source in ("personal", "official"):
                sources.append(
                    SourceReference(
                        source=event.source,
                        id=str(event.source_event_id),
                        title=event.title,
                        version=event.version,
                        locator=f"dates:{now.date()}:{ends_at.date()}",
                    )
                )
            for other in ordered[index + 1 :]:
                if other.starts_at >= event.ends_at:
                    break
                if conflicts >= 100:
                    warnings.append("conflicts_partial")
                    break
                conflicts += 1
                issues.append(
                    {
                        "kind": "conflict",
                        "events": [event.id, other.id],
                        "versions": [event.version, other.version],
                        "task_ids": [
                            str(item.task_id)
                            for item in (event, other)
                            if isinstance(item, WorkSessionBusy) and item.task_id in active_ids
                        ],
                        "times": [
                            event.starts_at.isoformat(),
                            event.ends_at.isoformat(),
                            other.starts_at.isoformat(),
                            other.ends_at.isoformat(),
                        ],
                    }
                )
        if not preferences.windows:
            warnings.append("work_windows_not_configured")
        else:
            free_minutes = sum(
                int((slot.ends_at - slot.starts_at).total_seconds() // 60)
                for slot in (capacity or availability).free
            )
            parents = {
                task.parent_id for task in active if task.parent_id is not None
            } | excluded_parents
            if any(task.id in parents for task in active):
                warnings.append("parent_effort_excluded")
            if any(task.deadline_at is None for task in active):
                warnings.append("undated_work_not_assigned_to_week")
            due = [
                task
                for task in active
                if task.id not in parents
                and task.deadline_at is not None
                and task.deadline_at <= ends_at
            ]
            unknown = [task for task in due if task.remaining_minutes is None]
            if unknown:
                warnings.append("remaining_work_unknown")
            checkpoints = sorted(
                {
                    task.deadline_at
                    for task in due
                    if task.deadline_at is not None and task.deadline_at > now
                }
            )
            for until in [*checkpoints, ends_at]:
                required = [
                    task
                    for task in due
                    if task.deadline_at is not None and task.deadline_at <= until
                ]
                demand = sum(task.remaining_minutes or 0 for task in required)
                available = sum(
                    max(0, int((min(slot.ends_at, until) - slot.starts_at).total_seconds() // 60))
                    for slot in (capacity or availability).free
                )
                # Remaining work is a lower bound; reserved sessions never establish progress.
                if demand > available:
                    issues.append(
                        {
                            "kind": "overload",
                            "tasks": [
                                [str(task.id), task.version]
                                for task in required
                                if task.remaining_minutes is not None
                            ],
                            "before": until.isoformat() if until < ends_at else "next_7_days",
                            "known_remaining_minutes": demand,
                            "work_preferences_version": preferences.version,
                            "calendar_fingerprint": digest(
                                [
                                    [
                                        event.id,
                                        event.version,
                                        event.starts_at.isoformat(),
                                        event.ends_at.isoformat(),
                                    ]
                                    for event in ordered
                                ]
                            ),
                            "conditional": not availability.verified or incomplete_tasks,
                        }
                    )
                    break

    data = {
        "checked_at": now.isoformat(),
        "ends_at": ends_at.isoformat(),
        "tasks": [
            {
                "id": str(task.id),
                "title": task.title,
                "status": task.status,
                "deadline_at": task.deadline_at.isoformat() if task.deadline_at else None,
                "remaining_minutes": task.remaining_minutes,
                "estimated_minutes": task.estimated_minutes,
                "parent_id": str(task.parent_id) if task.parent_id else None,
            }
            for task in active
        ],
        "events": events,
        "free_work_minutes": free_minutes,
        "calendar_verified": availability.verified if availability else False,
        "sessions_are_not_progress": True,
    }
    return ReviewEvidence(data, tuple(sources), tuple(issues), tuple(dict.fromkeys(warnings)))
