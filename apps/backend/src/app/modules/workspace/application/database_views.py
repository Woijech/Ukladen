from collections.abc import Mapping
from dataclasses import dataclass, replace
from uuid import UUID, uuid4

from app.modules.workspace.application.database_content import DatabaseContentService, RecordResult
from app.modules.workspace.application.database_view_ports import DatabaseViewRepository
from app.modules.workspace.domain.database_views import DatabaseView, query_value, validate_query
from app.modules.workspace.domain.databases import DatabaseProperty
from app.modules.workspace.domain.organization import (
    InvalidWorkspaceInput,
    WorkspaceConflict,
    WorkspaceNotFound,
    organization_values,
    pagination,
    require_version,
)


@dataclass(frozen=True)
class TableResult:
    view: DatabaseView
    properties: list[DatabaseProperty]
    items: list[RecordResult]
    schema_version: int
    total: int
    limit: int
    offset: int


class DatabaseViewService:
    def __init__(self, repository: DatabaseViewRepository, content: DatabaseContentService) -> None:
        self.repository, self.content = repository, content
        self.databases, self.notes, self.now = content.databases, content.notes, content.now

    def get(self, user_id: UUID, database_id: UUID, view_id: UUID) -> DatabaseView:
        self.databases.get(user_id, database_id, active=True)
        view = self.repository.get(user_id, database_id, view_id)
        if view is None:
            raise WorkspaceNotFound()
        return view

    def list(
        self, user_id: UUID, database_id: UUID, limit: int = 100, offset: int = 0
    ) -> list[DatabaseView]:
        self.databases.get(user_id, database_id, active=True)
        pagination(limit, offset)
        return self.repository.list(user_id, database_id, limit, offset)

    def create(
        self,
        user_id: UUID,
        database_id: UUID,
        expected_schema_version: int,
        name: str,
        color: str | None = None,
        query: object = None,
    ) -> DatabaseView:
        _, definitions = self.content.schema(
            user_id, database_id, expected_schema_version=expected_schema_version, write=True
        )
        name, color = organization_values(name, color)
        normalized = validate_query({} if query is None else query, definitions)
        now = self.now()
        view = DatabaseView(
            id=uuid4(),
            user_id=user_id,
            database_id=database_id,
            name=name,
            color=color,
            query=normalized,
            version=1,
            created_at=now,
            updated_at=now,
        )
        self.repository.create(view)
        return view

    def update(
        self,
        user_id: UUID,
        database_id: UUID,
        view_id: UUID,
        expected_version: int,
        expected_schema_version: int,
        changes: Mapping[str, object],
    ) -> DatabaseView:
        _, definitions = self.content.schema(
            user_id, database_id, expected_schema_version=expected_schema_version, write=True
        )
        view = self.get(user_id, database_id, view_id)
        require_version(view.version, expected_version)
        if not changes or changes.keys() - {"name", "color", "query"}:
            raise InvalidWorkspaceInput()
        name, color = organization_values(
            changes.get("name", view.name), changes.get("color", view.color)
        )
        query = validate_query(changes.get("query", query_value(view.query)), definitions)
        updated = replace(
            view,
            name=name,
            color=color,
            query=query,
            version=view.version + 1,
            updated_at=self.now(),
        )
        self.repository.save(updated, expected_version)
        return updated

    def delete(
        self, user_id: UUID, database_id: UUID, view_id: UUID, expected_version: int
    ) -> None:
        self.notes.require_user(user_id, write=True)
        view = self.get(user_id, database_id, view_id)
        require_version(view.version, expected_version)
        self.repository.delete(view, expected_version)

    def table(
        self, user_id: UUID, database_id: UUID, view_id: UUID, limit: int = 100, offset: int = 0
    ) -> TableResult:
        pagination(limit, offset)
        view = self.get(user_id, database_id, view_id)
        database, definitions = self.content.schema(user_id, database_id)
        try:
            query = validate_query(query_value(view.query), definitions)
        except InvalidWorkspaceInput:
            raise WorkspaceConflict() from None
        # shortcut: scan <=10000 page refs; add indexed page queries when raising the limit.
        candidates = self.repository.candidates(user_id, database_id, query, definitions)
        if len(candidates) > 10000:
            raise WorkspaceConflict()
        pages = self.notes.summaries(user_id, tuple(item.page_id for item in candidates))
        selected = [
            item
            for item in candidates
            if item.page_id in pages and pages[item.page_id].trashed_at is None
        ]
        active = {item.id: item for item in definitions if item.trashed_at is None}
        columns = (
            [active[identifier] for identifier in query.columns]
            if query.columns is not None
            else list(active.values())
        )
        keys = {str(item.id) for item in columns}
        batch = selected[offset : offset + limit]
        records = {
            item.id: item
            for item in self.repository.records(
                user_id, database_id, tuple(item.id for item in batch)
            )
        }
        items = [
            RecordResult(
                replace(
                    records[item.id],
                    values={
                        key: value for key, value in records[item.id].values.items() if key in keys
                    },
                ),
                pages[item.page_id],
                database.schema_version,
            )
            for item in batch
        ]
        return TableResult(
            view, columns, items, database.schema_version, len(selected), limit, offset
        )
