from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.ai.application.task_actions import TaskCreateAction
from app.modules.relations.application.task_links import TaskRelationService
from app.modules.tasks.application.service import TaskService
from app.modules.tasks.infrastructure.orm import TaskOriginModel


class SqlAlchemyTaskOrigins:
    def __init__(self, database: Session, tasks: TaskService, relations: TaskRelationService):
        self.database, self.tasks, self.relations = database, tasks, relations

    def save(self, user_id: UUID, task_id: UUID, action: TaskCreateAction) -> None:
        self.tasks.get(user_id, task_id)
        self.database.add(
            TaskOriginModel(
                task_id=task_id,
                user_id=user_id,
                provenance=action.model_dump(
                    mode="json", include={"sources", "estimate_kind", "uncertainties"}
                ),
            )
        )
        for source in action.sources:
            if source.source == "page":
                self.relations.link(user_id, task_id, UUID(source.id))
        self.database.flush()
