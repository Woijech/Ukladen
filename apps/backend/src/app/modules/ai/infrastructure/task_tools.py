from dataclasses import asdict
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.ai.application.source_queries import PlanRead, PlanStatusRead, TaskRead
from app.modules.ai.application.sources import json_value
from app.modules.calendar.application.availability import CalendarAvailabilityService
from app.modules.calendar.application.service import CalendarService
from app.modules.search.application.evidence import EvidenceResult
from app.modules.search.domain.evidence import SourceReference
from app.modules.tasks.application.dependencies import TaskDependencyService
from app.modules.tasks.application.planning import PlanningService
from app.modules.tasks.application.plans import PlanService
from app.modules.tasks.application.service import TaskService
from app.modules.tasks.infrastructure.dependencies import SqlAlchemyTaskDependencies
from app.modules.tasks.infrastructure.planning import SqlAlchemyPlanning
from app.modules.tasks.infrastructure.plans import SqlAlchemyPlans
from app.modules.tasks.infrastructure.repository import SqlAlchemyTaskRepository
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication


def task_service(database: Session) -> TaskService:
    return TaskService(SqlAlchemyTaskRepository(database), SqlAlchemyUserAuthentication(database))


def read_tasks(database: Session, user_id: UUID, query: TaskRead) -> EvidenceResult:
    tasks = task_service(database)
    if query.task_id is not None:
        task = tasks.get(user_id, query.task_id)
        if task.trashed_at is not None:
            return EvidenceResult(status="not_found")
        predecessors, unresolved = TaskDependencyService(
            tasks, SqlAlchemyTaskDependencies(database)
        ).list(user_id, task.id, query.limit, query.offset)
        values = asdict(task)
        values.pop("user_id")
        description = task.description or ""
        values["description"] = description[:2000]
        values["predecessors"] = [
            {
                "id": str(item.id),
                "title": item.title,
                "version": item.version,
                "status": item.status,
                "trashed_at": str(item.trashed_at) if item.trashed_at else None,
            }
            for item in predecessors
        ]
        values["has_unresolved_dependencies"] = unresolved
        values["origin"] = tasks.origin(user_id, task.id)
        return EvidenceResult(
            data=json_value(values),
            sources=(
                SourceReference(
                    source="task",
                    id=str(task.id),
                    version=task.version,
                    title=task.title,
                    locator="task:details",
                ),
            ),
            coverage="partial",
            warnings=(
                "task_description_and_dependencies_bounded",
                "sessions_never_establish_progress",
            ),
            next_offset=query.offset + len(predecessors)
            if len(predecessors) == query.limit
            else None,
        )
    if query.task_ids:
        selected = [tasks.get(user_id, identifier) for identifier in query.task_ids]
        selected = [item for item in selected if item.trashed_at is None]
        items = selected[query.offset : query.offset + query.limit]
        more = query.offset + len(items) < len(selected)
    else:
        items = tasks.list(user_id, offset=query.offset, limit=query.limit)
        more = len(items) == query.limit
    return EvidenceResult(
        data=json_value(
            [
                {
                    key: value
                    for key, value in asdict(item).items()
                    if key not in ("user_id", "description")
                }
                for item in items
            ]
        ),
        sources=tuple(
            SourceReference(
                source="task",
                id=str(item.id),
                version=item.version,
                title=item.title,
                locator="task:summary",
            )
            for item in items
        ),
        coverage="partial" if more or query.offset else "complete",
        next_offset=query.offset + len(items) if more else None,
    )


def read_plan(
    database: Session, calendar: CalendarService, user_id: UUID, query: PlanRead | PlanStatusRead
) -> EvidenceResult:
    repository = SqlAlchemyPlanning(database)
    plans = PlanService(
        PlanningService(
            task_service(database), repository, CalendarAvailabilityService(calendar, repository)
        ),
        SqlAlchemyPlans(database),
    )
    plan = (
        plans.propose(user_id, query.request)
        if isinstance(query, PlanRead)
        else plans.validate(user_id, query.plan_id, query.digest)
    )
    return EvidenceResult(
        data=json_value(
            {
                "plan_id": plan.id,
                "digest": plan.digest,
                "timezone": plan.timezone,
                "verified": plan.verified,
                "sessions": [item.model_dump(mode="json") for item in plan.sessions[:10]],
                "session_count": len(plan.sessions),
                "cancelled_session_count": len(plan.cancelled_sessions),
                "unplaced": [item.model_dump(mode="json") for item in plan.unplaced[:20]],
                "unplaced_count": len(plan.unplaced),
                "warnings": plan.warnings,
                "status": plan.status,
            }
        ),
        coverage="partial",
        warnings=("complete_exact_plan_will_be_shown_for_owner_confirmation",),
    )
