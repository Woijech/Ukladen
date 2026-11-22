"""Notes' read-only adapter for owned workspace view references."""

from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.modules.workspace.infrastructure.orm import DatabaseModel, DatabaseViewModel


class SqlAlchemyEmbeddedViews:
    def __init__(self, session: Session) -> None:
        self.session = session

    def owned(self, user_id: UUID, references: tuple[tuple[UUID, UUID], ...]) -> bool:
        if not references:
            return True
        found = {
            (database_id, view_id)
            for database_id, view_id in self.session.execute(
                select(DatabaseViewModel.database_id, DatabaseViewModel.id)
                .join(
                    DatabaseModel,
                    (DatabaseModel.id == DatabaseViewModel.database_id)
                    & (DatabaseModel.user_id == DatabaseViewModel.user_id),
                )
                .where(
                    DatabaseViewModel.user_id == user_id,
                    DatabaseModel.trashed_at.is_(None),
                    tuple_(DatabaseViewModel.database_id, DatabaseViewModel.id).in_(references),
                )
            )
        }
        return found == set(references)
