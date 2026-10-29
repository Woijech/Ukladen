"""Read owned review inputs through the existing workspace application services."""

from dataclasses import asdict, replace
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.ai.application.review_evidence import ReviewEvidence, review_facts
from app.modules.ai.application.reviews import ReviewConfiguration
from app.modules.ai.application.source_queries import (
    CalendarRead,
    SearchRead,
    restrict_source_query,
)
from app.modules.ai.infrastructure.sources import SqlAlchemySourceReader
from app.modules.ai.infrastructure.task_tools import task_service
from app.modules.calendar.application.availability import CalendarAvailabilityService
from app.modules.search.domain.evidence import source_fingerprint
from app.modules.tasks.domain.tasks import InvalidTaskInput, TaskNotFound
from app.modules.tasks.infrastructure.planning import SqlAlchemyPlanning
from app.modules.users.domain.profile import ProfileUnavailable
from app.modules.users.infrastructure.repository import SqlAlchemyProfileRepository


def collect_review(
    database: Session,
    reader: SqlAlchemySourceReader,
    user_id: UUID,
    configuration: ReviewConfiguration,
    now: datetime,
) -> ReviewEvidence:
    database.execute(text("SET LOCAL statement_timeout = '5s'"))
    profile = SqlAlchemyProfileRepository(database).get_active(user_id)
    if profile is None:
        raise ProfileUnavailable()
    workspace = reader.service(database)
    tasks = task_service(database)
    scope = configuration.source_scope
    incomplete = False
    if scope is not None:
        selected = []
        for identifier in scope.task_ids:
            try:
                selected.append(tasks.get(user_id, identifier))
            except TaskNotFound:
                continue
    else:
        selected = tasks.list(user_id, status="todo", limit=200)
        in_progress = tasks.list(user_id, status="in_progress", limit=200)
        incomplete = len(selected) == 200 or len(in_progress) == 200
        selected.extend(in_progress)
    active = [
        task
        for task in selected
        if task.status in ("todo", "in_progress") and task.trashed_at is None
    ]
    extra_warnings = []
    if scope is None:
        excluded_parents = frozenset(
            task.id for task in active if tasks.repository.has_open_descendants(user_id, task.id)
        )
    else:
        selected_ids = {task.id for task in active}
        excluded_parents = frozenset(
            task.parent_id
            for task in active
            if task.parent_id is not None and task.parent_id in selected_ids
        )
        if len(active) > 1 and any(
            task.parent_id is not None and task.parent_id not in selected_ids for task in active
        ):
            extra_warnings.append("scope_hierarchy_uncertain")
    planning = SqlAlchemyPlanning(database)
    preferences = planning.preferences(user_id)
    availability = capacity = None
    ends_at = now + timedelta(days=7)
    if scope is None or scope.calendar:
        try:
            windows = preferences.expand(now, ends_at, profile.timezone)
        except InvalidTaskInput:
            windows = []
            extra_warnings.append("work_windows_dst_unresolved")
        service = CalendarAvailabilityService(workspace.calendar.calendar, planning)
        availability = service.read(user_id, now, ends_at, windows)
        selected_ids = {
            task.id
            for task in selected
            if task.status in ("todo", "in_progress")
            and task.trashed_at is None
            and task.id not in excluded_parents
            and task.deadline_at is not None
            and task.deadline_at <= ends_at
            and task.remaining_minutes is not None
        }
        reserved = frozenset(
            session.id
            for session in planning.sessions(user_id, now, ends_at)
            if session.task_id in selected_ids and not session.cancelled
        )
        capacity = service.read(user_id, now, ends_at, windows, exclude_work_session_ids=reserved)
    evidence = review_facts(
        selected,
        availability,
        preferences,
        now,
        incomplete_tasks=incomplete,
        capacity=capacity,
        excluded_parents=excluded_parents,
    )
    if {"work_windows_dst_unresolved", "scope_hierarchy_uncertain"}.intersection(extra_warnings):
        evidence = replace(
            evidence,
            issues=tuple(issue for issue in evidence.issues if issue["kind"] != "overload"),
            data=evidence.data | {"free_work_minutes": None},
        )
    data: dict = evidence.data | {
        "timezone": profile.timezone,
        "work_preferences_version": preferences.version,
    }
    preview_sources = []
    if availability is not None:
        zone = ZoneInfo(profile.timezone)
        preview = workspace.read(
            user_id,
            CalendarRead(
                date_from=now.astimezone(zone).date(),
                date_to=ends_at.astimezone(zone).date(),
                database_view_ids=(),
                limit=20,
            ),
        )
        if isinstance(preview.data, dict):
            entries = preview.data.get("entries", [])
            if isinstance(entries, list):
                data["events"] = [
                    entry
                    for entry in cast(list[dict], entries)
                    if datetime.fromisoformat(entry["starts_at"]) < ends_at
                    and datetime.fromisoformat(entry["ends_at"]) > now
                ] + [event for event in data["events"] if event["id"].startswith("task_session:")]
        preview_sources = list(preview.sources)
        if preview.next_offset is not None:
            extra_warnings.append("calendar_preview_partial")
    # Calendar facts without a revision (official occurrences) require a content fingerprint.
    if availability is not None:
        facts = {(event.source, str(event.source_event_id)): event for event in availability.events}
        evidence = replace(
            evidence,
            sources=tuple(
                source.model_copy(
                    update={
                        "fingerprint": source_fingerprint(asdict(facts[(source.source, source.id)]))
                    }
                )
                if (source.source, source.id) in facts
                else source
                for source in evidence.sources
            ),
        )
    related = []
    visible_ids = {task["id"] for task in data["tasks"][:30]}
    visible_events = {event["id"].split(":", 1)[-1] for event in data["events"][:20]}
    problem_events = {
        event_id.split(":", 1)[-1]
        for issue in evidence.issues
        for event_id in issue.get("events", [])
    }
    references = [
        ref
        for ref in (*evidence.sources, *preview_sources)
        if ref.id in visible_ids | visible_events
    ]
    conflict_references = [
        ref for ref in (*evidence.sources, *preview_sources) if ref.id in problem_events
    ]
    if configuration.materials:
        topics = [
            task.title
            for task in selected
            if task.status in ("todo", "in_progress") and task.trashed_at is None
        ]
        if availability:
            topics.extend(event.title for event in availability.events)
        for topic in dict.fromkeys(topics[:3]):
            for source_type in ("page", "material"):
                query = restrict_source_query(
                    SearchRead(query=topic[:200], source=source_type, limit=2), scope
                )
                if query is None:
                    continue
                result = workspace.read(user_id, query)
                if result.status == "ok" and result.sources:
                    related.append({"topic": topic, "matches": result.data})
                    references.extend(result.sources)
    references.extend(conflict_references)
    data["related_materials"] = related
    # The report is a bounded briefing, never a claim to read every source in full.
    data["task_count"] = len(data["tasks"])
    data["event_count"] = len(data["events"])
    if len(data["tasks"]) > 30 or len(data["events"]) > 20 or len(evidence.issues) > 30:
        extra_warnings.append("briefing_evidence_partial")
    data["tasks"] = data["tasks"][:30]
    data["events"] = data["events"][:20]
    references = list({(ref.source, ref.id, ref.locator): ref for ref in references}.values())
    if len(references) > 64:
        extra_warnings.append("source_links_partial")
    return replace(
        evidence,
        data=data,
        sources=tuple(references[:64]),
        warnings=tuple(dict.fromkeys([*evidence.warnings, *extra_warnings])),
    )
