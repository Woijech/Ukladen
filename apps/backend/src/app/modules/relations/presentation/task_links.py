from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.modules.academics.presentation.routes import no_store
from app.modules.auth.presentation.dependencies import (
    CurrentSession,
    Database,
    get_current_session,
    require_csrf,
)
from app.modules.notes.presentation.routes import Notes
from app.modules.notes.presentation.schemas import PageSummary
from app.modules.relations.application.task_links import TaskRelationService
from app.modules.relations.infrastructure.task_links import SqlAlchemyTaskPageLinks
from app.modules.tasks.presentation.routes import Tasks
from app.modules.tasks.presentation.schemas import TaskSummaryResponse

router = APIRouter(
    prefix="/api/v1/relations",
    tags=["relations"],
    dependencies=[Depends(no_store), Depends(get_current_session)],
)


def get_task_relations(database: Database, notes: Notes, tasks: Tasks) -> TaskRelationService:
    return TaskRelationService(SqlAlchemyTaskPageLinks(database), notes, tasks)


TaskRelations = Annotated[TaskRelationService, Depends(get_task_relations)]


class TaskPagesResponse(BaseModel):
    items: list[PageSummary]
    limit: int
    offset: int


class PageTasksResponse(BaseModel):
    items: list[TaskSummaryResponse]
    limit: int
    offset: int


@router.put(
    "/tasks/{task_id}/pages/{page_id}",
    response_model=PageSummary,
    dependencies=[Depends(require_csrf)],
)
def link_task_page(
    task_id: UUID,
    page_id: UUID,
    current: CurrentSession,
    database: Database,
    relations: TaskRelations,
) -> PageSummary:
    with database.begin():
        return PageSummary.model_validate(relations.link(current.user_id, task_id, page_id))


@router.delete(
    "/tasks/{task_id}/pages/{page_id}", status_code=204, dependencies=[Depends(require_csrf)]
)
def unlink_task_page(
    task_id: UUID,
    page_id: UUID,
    current: CurrentSession,
    database: Database,
    relations: TaskRelations,
) -> None:
    with database.begin():
        relations.unlink(current.user_id, task_id, page_id)


@router.get("/tasks/{task_id}/pages", response_model=TaskPagesResponse)
def task_pages(
    task_id: UUID,
    current: CurrentSession,
    database: Database,
    relations: TaskRelations,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0, le=2**31 - 1)] = 0,
) -> TaskPagesResponse:
    with database.begin():
        database.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        return TaskPagesResponse(
            items=[
                PageSummary.model_validate(item)
                for item in relations.for_task(current.user_id, task_id, limit, offset)
            ],
            limit=limit,
            offset=offset,
        )


@router.get("/pages/{page_id}/tasks", response_model=PageTasksResponse)
def page_tasks(
    page_id: UUID,
    current: CurrentSession,
    database: Database,
    relations: TaskRelations,
    tasks: Tasks,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0, le=2**31 - 1)] = 0,
) -> PageTasksResponse:
    with database.begin():
        database.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        return PageTasksResponse(
            items=[
                TaskSummaryResponse.from_task(item, tasks.now())
                for item in relations.for_page(current.user_id, page_id, limit, offset)
            ],
            limit=limit,
            offset=offset,
        )
