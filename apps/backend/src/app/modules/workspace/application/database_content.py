import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from uuid import UUID, uuid4

from app.modules.notes.domain.pages import PageMetadata
from app.modules.workspace.application.database_content_ports import DatabaseContentRepository
from app.modules.workspace.application.databases import DatabaseService
from app.modules.workspace.domain.databases import DatabaseProperty, DatabaseRecord, UserDatabase
from app.modules.workspace.domain.organization import (
    InvalidWorkspaceInput,
    WorkspaceConflict,
    WorkspaceNotFound,
    pagination,
    require_version,
)
from app.modules.workspace.domain.properties import (
    PropertyValue,
    convert_property_value,
    property_id,
    property_spec,
    property_value,
)


@dataclass(frozen=True)
class PropertyResult:
    property: DatabaseProperty
    schema_version: int


@dataclass(frozen=True)
class RecordResult:
    record: DatabaseRecord
    page: PageMetadata
    schema_version: int


class DatabaseContentService:
    def __init__(self, repository: DatabaseContentRepository, databases: DatabaseService) -> None:
        self.repository, self.databases = repository, databases
        self.notes, self.now = databases.notes, databases.now

    def schema(
        self,
        user_id: UUID,
        database_id: UUID,
        *,
        expected_schema_version: int | None = None,
        write: bool = False,
    ) -> tuple[UserDatabase, list[DatabaseProperty]]:
        self.notes.require_user(user_id, write=write)
        database = self.databases.get(user_id, database_id, active=True)
        if write and expected_schema_version is None:
            raise InvalidWorkspaceInput()
        if expected_schema_version is not None:
            require_version(database.schema_version, expected_schema_version)
        return database, self.repository.properties(user_id, database_id)

    def changed_schema(self, database: UserDatabase) -> int:
        updated = replace(
            database,
            schema_version=database.schema_version + 1,
            version=database.version + 1,
            updated_at=self.now(),
        )
        self.databases.repository.save(updated, database.version)
        return updated.schema_version

    @staticmethod
    def definition(
        properties: list[DatabaseProperty], identifier: UUID, *, active: bool = False
    ) -> DatabaseProperty:
        definition = next((item for item in properties if item.id == identifier), None)
        if definition is None:
            raise WorkspaceNotFound()
        if active and definition.trashed_at is not None:
            raise WorkspaceConflict()
        return definition

    def create_property(
        self,
        user_id: UUID,
        database_id: UUID,
        expected_schema_version: int,
        name: str,
        kind: str,
        options: object = (),
    ) -> PropertyResult:
        database, definitions = self.schema(
            user_id, database_id, expected_schema_version=expected_schema_version, write=True
        )
        if len(definitions) >= 100:
            raise WorkspaceConflict()
        spec = property_spec(name, kind, options)
        now = self.now()
        definition = DatabaseProperty(
            id=uuid4(),
            user_id=user_id,
            database_id=database_id,
            name=spec.name,
            kind=spec.kind,
            options=spec.options,
            position=len(definitions),
            version=1,
            created_at=now,
            updated_at=now,
        )
        self.repository.create_property(definition)
        return PropertyResult(definition, self.changed_schema(database))

    def update_property(
        self,
        user_id: UUID,
        database_id: UUID,
        identifier: UUID,
        expected_version: int,
        expected_schema_version: int,
        changes: Mapping[str, object],
    ) -> PropertyResult:
        database, definitions = self.schema(
            user_id, database_id, expected_schema_version=expected_schema_version, write=True
        )
        definition = self.definition(definitions, identifier, active=True)
        require_version(definition.version, expected_version)
        if not changes or changes.keys() - {"name", "kind", "options", "position"}:
            raise InvalidWorkspaceInput()
        options = changes.get(
            "options", [{"id": item.id, "name": item.name} for item in definition.options]
        )
        spec = property_spec(
            changes.get("name", definition.name), changes.get("kind", definition.kind), options
        )
        position = changes.get("position", definition.position)
        if type(position) is not int or not 0 <= position <= 100000:
            raise InvalidWorkspaceInput()
        updated = replace(
            definition,
            name=spec.name,
            kind=spec.kind,
            options=spec.options,
            position=position,
            version=definition.version + 1,
            updated_at=self.now(),
        )
        conversions: list[tuple[UUID, int, PropertyValue]] = []
        for record_id, version, value in self.repository.property_values(
            user_id, database_id, identifier
        ):
            converted = convert_property_value(definition, updated, value)
            if converted != value:
                conversions.append((record_id, version, converted))
        self.repository.convert_values(user_id, database_id, identifier, conversions, self.now())
        self.repository.save_property(updated, expected_version)
        return PropertyResult(updated, self.changed_schema(database))

    def property_lifecycle(
        self,
        user_id: UUID,
        database_id: UUID,
        identifier: UUID,
        expected_version: int,
        expected_schema_version: int,
        *,
        restore: bool = False,
    ) -> PropertyResult:
        database, definitions = self.schema(
            user_id, database_id, expected_schema_version=expected_schema_version, write=True
        )
        definition = self.definition(definitions, identifier)
        require_version(definition.version, expected_version)
        if (definition.trashed_at is not None) != restore:
            raise WorkspaceConflict()
        now = self.now()
        updated = replace(
            definition,
            trashed_at=None if restore else now,
            version=definition.version + 1,
            updated_at=now,
        )
        self.repository.save_property(updated, expected_version)
        return PropertyResult(updated, self.changed_schema(database))

    @staticmethod
    def normalized_values(
        definitions: list[DatabaseProperty],
        values: object,
        current: Mapping[str, PropertyValue] | None = None,
    ) -> dict[str, PropertyValue]:
        if not isinstance(values, Mapping) or len(values) > 100:
            raise InvalidWorkspaceInput()
        available = {item.id: item for item in definitions if item.trashed_at is None}
        updates: dict[str, PropertyValue] = {}
        for identifier, value in values.items():
            key = property_id(identifier)
            if key not in available or str(key) in updates:
                raise InvalidWorkspaceInput()
            updates[str(key)] = property_value(available[key], value)
        merged = dict(current or {}) | updates
        normalized: dict[str, PropertyValue] = {
            key: value for key, value in merged.items() if value is not None
        }
        if (
            len(normalized) > 100
            or len(json.dumps(normalized, ensure_ascii=False, allow_nan=False).encode("utf-8"))
            > 131072
        ):
            raise InvalidWorkspaceInput()
        return normalized

    def record(
        self, user_id: UUID, database_id: UUID, record_id: UUID, *, active: bool = False
    ) -> DatabaseRecord:
        record = self.repository.get_record(user_id, database_id, record_id)
        if record is None:
            raise WorkspaceNotFound()
        if active and record.trashed_at is not None:
            raise WorkspaceConflict()
        return record

    def detail(
        self, database: UserDatabase, definitions: list[DatabaseProperty], record: DatabaseRecord
    ) -> RecordResult:
        active_ids = {str(item.id) for item in definitions if item.trashed_at is None}
        visible = replace(
            record, values={key: value for key, value in record.values.items() if key in active_ids}
        )
        return RecordResult(
            visible, self.notes.summary(record.user_id, record.page_id), database.schema_version
        )

    def get_record(self, user_id: UUID, database_id: UUID, record_id: UUID) -> RecordResult:
        database, definitions = self.schema(user_id, database_id)
        return self.detail(database, definitions, self.record(user_id, database_id, record_id))

    def list_records(
        self,
        user_id: UUID,
        database_id: UUID,
        trashed: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RecordResult]:
        pagination(limit, offset)
        database, definitions = self.schema(user_id, database_id)
        return [
            self.detail(database, definitions, record)
            for record in self.repository.list_records(user_id, database_id, trashed, limit, offset)
        ]

    def create_record(
        self,
        user_id: UUID,
        database_id: UUID,
        expected_schema_version: int,
        values: object,
        *,
        page_id: UUID | None = None,
        title: str | None = None,
    ) -> RecordResult:
        database, definitions = self.schema(
            user_id, database_id, expected_schema_version=expected_schema_version, write=True
        )
        normalized = self.normalized_values(definitions, values)
        if (page_id is None) == (title is None):
            raise InvalidWorkspaceInput()
        if self.repository.record_count(user_id, database_id) >= 10000:
            raise WorkspaceConflict()
        page = (
            self.notes.summary(user_id, page_id, active=True)
            if page_id is not None
            else self.notes.create(user_id, title or "")
        )
        if self.repository.record_for_page(user_id, database_id, page.id) is not None:
            raise WorkspaceConflict()
        now = self.now()
        record = DatabaseRecord(
            id=uuid4(),
            user_id=user_id,
            database_id=database_id,
            page_id=page.id,
            values=normalized,
            version=1,
            created_at=now,
            updated_at=now,
        )
        self.repository.create_record(record)
        return RecordResult(record, page, database.schema_version)

    def update_record(
        self,
        user_id: UUID,
        database_id: UUID,
        record_id: UUID,
        expected_version: int,
        expected_schema_version: int,
        values: Mapping[str, object],
    ) -> RecordResult:
        database, definitions = self.schema(
            user_id, database_id, expected_schema_version=expected_schema_version, write=True
        )
        record = self.record(user_id, database_id, record_id, active=True)
        require_version(record.version, expected_version)
        self.notes.summary(user_id, record.page_id, active=True)
        if not values:
            raise InvalidWorkspaceInput()
        normalized = self.normalized_values(definitions, values, record.values)
        updated = replace(
            record, values=normalized, version=record.version + 1, updated_at=self.now()
        )
        self.repository.save_record(updated, expected_version)
        return self.detail(database, definitions, updated)

    def record_lifecycle(
        self,
        user_id: UUID,
        database_id: UUID,
        record_id: UUID,
        expected_version: int,
        *,
        restore: bool = False,
    ) -> RecordResult:
        self.notes.require_user(user_id, write=True)
        database, definitions = self.schema(user_id, database_id)
        record = self.record(user_id, database_id, record_id)
        require_version(record.version, expected_version)
        if (record.trashed_at is not None) != restore:
            raise WorkspaceConflict()
        if restore:
            self.notes.summary(user_id, record.page_id, active=True)
        now = self.now()
        updated = replace(
            record, trashed_at=None if restore else now, version=record.version + 1, updated_at=now
        )
        self.repository.save_record(updated, expected_version)
        return self.detail(database, definitions, updated)

    def page_records(
        self, user_id: UUID, page_id: UUID, limit: int = 100, offset: int = 0
    ) -> list[RecordResult]:
        self.notes.summary(user_id, page_id)
        pagination(limit, offset)
        result = []
        for record in self.repository.page_records(user_id, page_id, limit, offset):
            database, definitions = self.schema(user_id, record.database_id)
            result.append(self.detail(database, definitions, record))
        return result
