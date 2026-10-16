from dataclasses import asdict
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.modules.workspace.domain.databases import UserDatabase
from app.modules.workspace.domain.organization import WorkspaceConflict
from app.modules.workspace.infrastructure.orm import DatabaseModel


def database_entity(row: DatabaseModel) -> UserDatabase:
    return UserDatabase(
        id=row.id,
        user_id=row.user_id,
        name=row.name,
        color=row.color,
        version=row.version,
        schema_version=row.schema_version,
        created_at=row.created_at,
        updated_at=row.updated_at,
        trashed_at=row.trashed_at,
    )


class SqlAlchemyDatabases:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, user_id: UUID, database_id: UUID) -> UserDatabase | None:
        row = self.session.scalar(
            select(DatabaseModel)
            .where(
                DatabaseModel.user_id == user_id,
                DatabaseModel.id == database_id,
            )
            .execution_options(populate_existing=True)
        )
        return database_entity(row) if row else None

    def list(self, user_id: UUID, trashed: bool, limit: int, offset: int) -> list[UserDatabase]:
        query = select(DatabaseModel).where(
            DatabaseModel.user_id == user_id,
            DatabaseModel.trashed_at.is_not(None)
            if trashed
            else DatabaseModel.trashed_at.is_(None),
        )
        return [
            database_entity(row)
            for row in self.session.scalars(
                query.order_by(DatabaseModel.created_at, DatabaseModel.id)
                .limit(limit)
                .offset(offset)
            )
        ]

    def create(self, database: UserDatabase) -> None:
        self.session.add(DatabaseModel(**asdict(database)))
        self.session.flush()

    def save(self, database: UserDatabase, expected_version: int) -> None:
        values = asdict(database)
        values.pop("id")
        values.pop("user_id")
        result = self.session.scalar(
            update(DatabaseModel)
            .where(
                DatabaseModel.user_id == database.user_id,
                DatabaseModel.id == database.id,
                DatabaseModel.version == expected_version,
            )
            .values(**values)
            .returning(DatabaseModel.id)
        )
        if result is None:
            raise WorkspaceConflict()
