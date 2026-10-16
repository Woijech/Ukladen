from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from app.modules.workspace.domain.database_views import DatabaseQuery, DatabaseView
from app.modules.workspace.domain.databases import DatabaseProperty, DatabaseRecord


@dataclass(frozen=True)
class RecordReference:
    id: UUID
    page_id: UUID


@dataclass(frozen=True)
class RecordDate:
    id: UUID
    page_id: UUID
    version: int
    value: object


class DatabaseViewRepository(Protocol):
    def get_owned(self, user_id: UUID, view_id: UUID) -> DatabaseView | None: ...
    def get(self, user_id: UUID, database_id: UUID, view_id: UUID) -> DatabaseView | None: ...
    def list(
        self, user_id: UUID, database_id: UUID, limit: int, offset: int
    ) -> list[DatabaseView]: ...
    def create(self, view: DatabaseView) -> None: ...
    def save(self, view: DatabaseView, expected_version: int) -> None: ...
    def delete(self, view: DatabaseView, expected_version: int) -> None: ...
    def candidates(
        self,
        user_id: UUID,
        database_id: UUID,
        query: DatabaseQuery,
        definitions: list[DatabaseProperty],
    ) -> list[RecordReference]: ...
    def records(
        self, user_id: UUID, database_id: UUID, record_ids: tuple[UUID, ...]
    ) -> list[DatabaseRecord]: ...
    def dates(
        self,
        user_id: UUID,
        view: DatabaseView,
        definitions: list[DatabaseProperty],
        date_from: date,
        date_to: date,
        starts_at: datetime,
        ends_at: datetime,
    ) -> list[RecordDate]: ...
