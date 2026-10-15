from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.modules.notes.application.service import NoteService
from app.modules.workspace.application.database_ports import DatabaseRepository
from app.modules.workspace.domain.databases import UserDatabase
from app.modules.workspace.domain.organization import (
    InvalidWorkspaceInput,
    WorkspaceConflict,
    WorkspaceNotFound,
    organization_values,
    pagination,
    require_version,
)


class DatabaseService:
    def __init__(
        self,
        repository: DatabaseRepository,
        notes: NoteService,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.repository, self.notes, self.now = repository, notes, now

    def get(self, user_id: UUID, database_id: UUID, *, active: bool = False) -> UserDatabase:
        self.notes.require_user(user_id)
        database = self.repository.get(user_id, database_id)
        if database is None:
            raise WorkspaceNotFound()
        if active and database.trashed_at is not None:
            raise WorkspaceConflict()
        return database

    def list(
        self, user_id: UUID, trashed: bool = False, limit: int = 100, offset: int = 0
    ) -> list[UserDatabase]:
        self.notes.require_user(user_id)
        pagination(limit, offset)
        if type(trashed) is not bool:
            raise InvalidWorkspaceInput()
        return self.repository.list(user_id, trashed, limit, offset)

    def create(self, user_id: UUID, name: str, color: str | None = None) -> UserDatabase:
        self.notes.require_user(user_id, write=True)
        name, color = organization_values(name, color)
        now = self.now()
        database = UserDatabase(
            id=uuid4(),
            user_id=user_id,
            name=name,
            color=color,
            version=1,
            schema_version=1,
            created_at=now,
            updated_at=now,
        )
        self.repository.create(database)
        return database

    def update(
        self, user_id: UUID, database_id: UUID, changes: Mapping[str, object], expected_version: int
    ) -> UserDatabase:
        self.notes.require_user(user_id, write=True)
        database = self.get(user_id, database_id, active=True)
        require_version(database.version, expected_version)
        if not changes or changes.keys() - {"name", "color"}:
            raise InvalidWorkspaceInput()
        name, color = organization_values(
            changes.get("name", database.name), changes.get("color", database.color)
        )
        updated = replace(
            database, name=name, color=color, version=database.version + 1, updated_at=self.now()
        )
        self.repository.save(updated, expected_version)
        return updated

    def lifecycle(
        self, user_id: UUID, database_id: UUID, expected_version: int, *, restore: bool = False
    ) -> UserDatabase:
        self.notes.require_user(user_id, write=True)
        database = self.get(user_id, database_id)
        require_version(database.version, expected_version)
        if (database.trashed_at is not None) != restore:
            raise WorkspaceConflict()
        now = self.now()
        updated = replace(
            database,
            trashed_at=None if restore else now,
            version=database.version + 1,
            updated_at=now,
        )
        self.repository.save(updated, expected_version)
        return updated
