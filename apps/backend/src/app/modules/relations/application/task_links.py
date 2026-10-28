from typing import Protocol
from uuid import UUID

from app.modules.notes.application.service import NoteService
from app.modules.notes.domain.pages import PageMetadata
from app.modules.relations.domain.links import InvalidRelationInput, RelationNotFound
from app.modules.tasks.application.service import TaskService
from app.modules.tasks.domain.tasks import Task, TaskTrashConflict


class TaskPageLinks(Protocol):
    def put(self, user_id: UUID, task_id: UUID, page_id: UUID) -> None: ...
    def delete(self, user_id: UUID, task_id: UUID, page_id: UUID) -> bool: ...
    def for_task(self, user_id: UUID, task_id: UUID, limit: int, offset: int) -> list[UUID]: ...
    def for_page(self, user_id: UUID, page_id: UUID, limit: int, offset: int) -> list[UUID]: ...


class TaskRelationService:
    def __init__(self, repository: TaskPageLinks, notes: NoteService, tasks: TaskService) -> None:
        self.repository, self.notes, self.tasks = repository, notes, tasks

    @staticmethod
    def pagination(limit: int, offset: int) -> None:
        if (
            type(limit) is not int
            or not 1 <= limit <= 200
            or type(offset) is not int
            or not 0 <= offset <= 2**31 - 1
        ):
            raise InvalidRelationInput()

    def link(self, user_id: UUID, task_id: UUID, page_id: UUID) -> PageMetadata:
        self.notes.require_user(user_id, write=True)
        task = self.tasks.get(user_id, task_id)
        if task.trashed_at is not None:
            raise TaskTrashConflict()
        page = self.notes.summary(user_id, page_id, active=True)
        self.repository.put(user_id, task_id, page_id)
        return page

    def unlink(self, user_id: UUID, task_id: UUID, page_id: UUID) -> None:
        self.notes.require_user(user_id, write=True)
        if not self.repository.delete(user_id, task_id, page_id):
            raise RelationNotFound()

    def for_task(self, user_id: UUID, task_id: UUID, limit: int, offset: int) -> list[PageMetadata]:
        self.tasks.get(user_id, task_id)
        self.pagination(limit, offset)
        return [
            self.notes.summary(user_id, identifier)
            for identifier in self.repository.for_task(user_id, task_id, limit, offset)
        ]

    def for_page(self, user_id: UUID, page_id: UUID, limit: int, offset: int) -> list[Task]:
        self.notes.summary(user_id, page_id)
        self.pagination(limit, offset)
        return [
            self.tasks.get(user_id, identifier)
            for identifier in self.repository.for_page(user_id, page_id, limit, offset)
        ]
