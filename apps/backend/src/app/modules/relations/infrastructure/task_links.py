from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.relations.infrastructure.orm import TaskPageLinkModel


class SqlAlchemyTaskPageLinks:
    def __init__(self, session: Session) -> None:
        self.session = session

    def put(self, user_id: UUID, task_id: UUID, page_id: UUID) -> None:
        self.session.execute(
            insert(TaskPageLinkModel)
            .values(user_id=user_id, task_id=task_id, page_id=page_id)
            .on_conflict_do_nothing(
                index_elements=[TaskPageLinkModel.task_id, TaskPageLinkModel.page_id]
            )
        )

    def delete(self, user_id: UUID, task_id: UUID, page_id: UUID) -> bool:
        return (
            self.session.scalar(
                delete(TaskPageLinkModel)
                .where(
                    TaskPageLinkModel.user_id == user_id,
                    TaskPageLinkModel.task_id == task_id,
                    TaskPageLinkModel.page_id == page_id,
                )
                .returning(TaskPageLinkModel.task_id)
            )
            is not None
        )

    def for_task(self, user_id: UUID, task_id: UUID, limit: int, offset: int) -> list[UUID]:
        return list(
            self.session.scalars(
                select(TaskPageLinkModel.page_id)
                .where(TaskPageLinkModel.user_id == user_id, TaskPageLinkModel.task_id == task_id)
                .order_by(TaskPageLinkModel.page_id)
                .limit(limit)
                .offset(offset)
            )
        )

    def for_page(self, user_id: UUID, page_id: UUID, limit: int, offset: int) -> list[UUID]:
        return list(
            self.session.scalars(
                select(TaskPageLinkModel.task_id)
                .where(TaskPageLinkModel.user_id == user_id, TaskPageLinkModel.page_id == page_id)
                .order_by(TaskPageLinkModel.task_id)
                .limit(limit)
                .offset(offset)
            )
        )
