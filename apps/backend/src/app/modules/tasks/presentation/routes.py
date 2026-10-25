import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse

from app.core.logging import log_failure
from app.modules.academics.presentation.routes import no_store
from app.modules.auth.presentation.dependencies import (
    CurrentSession,
    Database,
    get_current_session,
    require_csrf,
)
from app.modules.tasks.application.service import TaskService
from app.modules.tasks.domain.tasks import (
    InvalidTaskInput,
    TaskHierarchyConflict,
    TaskNotFound,
    TaskPriority,
    TaskStatus,
    TaskTrashConflict,
    TaskVersionConflict,
)
from app.modules.tasks.infrastructure.repository import SqlAlchemyTaskRepository
from app.modules.tasks.presentation.schemas import (
    TaskCreate,
    TaskListResponse,
    TaskPatch,
    TaskResponse,
    TaskSummaryResponse,
    TaskVersionRequest,
)
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/v1/tasks",
    tags=["tasks"],
    dependencies=[Depends(no_store), Depends(get_current_session)],
)


def get_tasks(database: Database) -> TaskService:
    return TaskService(SqlAlchemyTaskRepository(database), SqlAlchemyUserAuthentication(database))


Tasks = Annotated[TaskService, Depends(get_tasks)]


@router.post("", status_code=201, response_model=TaskResponse, dependencies=[Depends(require_csrf)])
def create_task(
    payload: TaskCreate,
    current: CurrentSession,
    database: Database,
    tasks: Tasks,
) -> TaskResponse:
    with database.begin():
        task = tasks.create(current.user_id, payload.model_dump())
        response = TaskResponse.from_task(task, tasks.now())
    logger.info("tasks.task_created", extra={"user_id": str(current.user_id)})
    return response


@router.get("", response_model=TaskListResponse)
def list_tasks(
    current: CurrentSession,
    database: Database,
    tasks: Tasks,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    parent_id: UUID | None = None,
    roots_only: bool = False,
    trashed: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0, le=2**31 - 1)] = 0,
) -> TaskListResponse:
    with database.begin():
        result = tasks.list(
            current.user_id,
            status=status,
            priority=priority,
            parent_id=parent_id,
            roots_only=roots_only,
            trashed=trashed,
            limit=limit,
            offset=offset,
        )
        now = tasks.now()
        return TaskListResponse(
            items=[TaskSummaryResponse.from_task(task, now) for task in result],
            limit=limit,
            offset=offset,
        )


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(
    task_id: UUID, current: CurrentSession, database: Database, tasks: Tasks
) -> TaskResponse:
    with database.begin():
        return TaskResponse.from_task(tasks.get(current.user_id, task_id), tasks.now())


@router.patch("/{task_id}", response_model=TaskResponse, dependencies=[Depends(require_csrf)])
def update_task(
    task_id: UUID,
    payload: TaskPatch,
    current: CurrentSession,
    database: Database,
    tasks: Tasks,
) -> TaskResponse:
    with database.begin():
        task = tasks.update(
            current.user_id,
            task_id,
            payload.model_dump(exclude_unset=True, exclude={"expected_version"}),
            payload.expected_version,
        )
        response = TaskResponse.from_task(task, tasks.now())
    logger.info("tasks.task_updated", extra={"user_id": str(current.user_id)})
    return response


@router.post("/{task_id}/trash", response_model=TaskResponse, dependencies=[Depends(require_csrf)])
def trash_task(
    task_id: UUID,
    payload: TaskVersionRequest,
    current: CurrentSession,
    database: Database,
    tasks: Tasks,
) -> TaskResponse:
    with database.begin():
        response = TaskResponse.from_task(
            tasks.trash(current.user_id, task_id, payload.expected_version), tasks.now()
        )
    logger.info("tasks.task_trashed", extra={"user_id": str(current.user_id)})
    return response


@router.post(
    "/{task_id}/restore", response_model=TaskResponse, dependencies=[Depends(require_csrf)]
)
def restore_task(
    task_id: UUID,
    payload: TaskVersionRequest,
    current: CurrentSession,
    database: Database,
    tasks: Tasks,
) -> TaskResponse:
    with database.begin():
        response = TaskResponse.from_task(
            tasks.restore(current.user_id, task_id, payload.expected_version), tasks.now()
        )
    logger.info("tasks.task_restored", extra={"user_id": str(current.user_id)})
    return response


def install_tasks(application: FastAPI) -> None:
    def task_error(request: Request, error: Exception) -> JSONResponse:
        if isinstance(error, InvalidTaskInput):
            status, detail, code = 422, "Invalid task input.", "invalid_task_input"
        elif isinstance(error, TaskNotFound):
            status, detail, code = 404, "Task not found.", "task_not_found"
        elif isinstance(error, TaskHierarchyConflict):
            status, detail, code = 409, "Task hierarchy conflict.", "task_hierarchy_conflict"
        elif isinstance(error, TaskTrashConflict):
            status, detail, code = 409, "Task trash conflict.", "task_trash_conflict"
        else:
            status, detail, code = 409, "Task changed. Reload and retry.", "task_version_conflict"
        log_failure(logger, "tasks.operation_rejected", error, level=logging.WARNING, reason=code)
        return JSONResponse(
            {"detail": detail, "code": code},
            status_code=status,
            headers={"Cache-Control": "no-store"},
        )

    for error_type in (
        InvalidTaskInput,
        TaskNotFound,
        TaskHierarchyConflict,
        TaskTrashConflict,
        TaskVersionConflict,
    ):
        application.add_exception_handler(error_type, task_error)
    application.include_router(router)
