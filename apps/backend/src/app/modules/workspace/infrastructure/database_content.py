from dataclasses import asdict
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.workspace.domain.databases import DatabaseProperty, DatabaseRecord
from app.modules.workspace.domain.organization import WorkspaceConflict
from app.modules.workspace.domain.properties import PropertyValue, property_spec
from app.modules.workspace.infrastructure.orm import (
    DatabaseModel,
    DatabasePropertyModel,
    DatabaseRecordModel,
)


def property_entity(row: DatabasePropertyModel) -> DatabaseProperty:
    spec = property_spec(row.name, row.kind, row.options)
    return DatabaseProperty(
        id=row.id,
        user_id=row.user_id,
        database_id=row.database_id,
        name=spec.name,
        kind=spec.kind,
        options=spec.options,
        position=row.position,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
        trashed_at=row.trashed_at,
    )


def property_columns(definition: DatabaseProperty) -> dict[str, object]:
    values = asdict(definition)
    values["options"] = [{"id": str(item.id), "name": item.name} for item in definition.options]
    return values


def record_entity(row: DatabaseRecordModel) -> DatabaseRecord:
    return DatabaseRecord(
        id=row.id,
        user_id=row.user_id,
        database_id=row.database_id,
        page_id=row.page_id,
        values=cast(dict[str, PropertyValue], row.values),
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
        trashed_at=row.trashed_at,
    )


class SqlAlchemyDatabaseContent:
    def __init__(self, session: Session) -> None:
        self.session = session

    def properties(self, user_id: UUID, database_id: UUID) -> list[DatabaseProperty]:
        return [
            property_entity(row)
            for row in self.session.scalars(
                select(DatabasePropertyModel)
                .where(
                    DatabasePropertyModel.user_id == user_id,
                    DatabasePropertyModel.database_id == database_id,
                )
                .order_by(DatabasePropertyModel.position, DatabasePropertyModel.id)
                .execution_options(populate_existing=True)
            )
        ]

    def create_property(self, definition: DatabaseProperty) -> None:
        self.session.add(DatabasePropertyModel(**property_columns(definition)))
        self.session.flush()

    def save_property(self, definition: DatabaseProperty, expected_version: int) -> None:
        values = property_columns(definition)
        for field in ("id", "user_id", "database_id"):
            values.pop(field)
        result = self.session.scalar(
            update(DatabasePropertyModel)
            .where(
                DatabasePropertyModel.user_id == definition.user_id,
                DatabasePropertyModel.database_id == definition.database_id,
                DatabasePropertyModel.id == definition.id,
                DatabasePropertyModel.version == expected_version,
            )
            .values(**values)
            .returning(DatabasePropertyModel.id)
        )
        if result is None:
            raise WorkspaceConflict()

    def property_values(
        self, user_id: UUID, database_id: UUID, property_id: UUID
    ) -> list[tuple[UUID, int, object]]:
        return [
            (identifier, version, value)
            for identifier, version, value in self.session.execute(
                select(
                    DatabaseRecordModel.id,
                    DatabaseRecordModel.version,
                    DatabaseRecordModel.values[str(property_id)],
                ).where(
                    DatabaseRecordModel.user_id == user_id,
                    DatabaseRecordModel.database_id == database_id,
                    DatabaseRecordModel.values.op("?")(str(property_id)),
                )
            )
        ]

    def convert_values(
        self,
        user_id: UUID,
        database_id: UUID,
        property_id: UUID,
        changes: list[tuple[UUID, int, PropertyValue]],
        now: datetime,
    ) -> None:
        for identifier, version, value in changes:
            expression = (
                DatabaseRecordModel.values.op("-")(str(property_id))
                if value is None
                else DatabaseRecordModel.values.op("||")({str(property_id): value})
            )
            try:
                result = self.session.scalar(
                    update(DatabaseRecordModel)
                    .where(
                        DatabaseRecordModel.user_id == user_id,
                        DatabaseRecordModel.database_id == database_id,
                        DatabaseRecordModel.id == identifier,
                        DatabaseRecordModel.version == version,
                    )
                    .values(values=expression, version=version + 1, updated_at=now)
                    .returning(DatabaseRecordModel.id)
                )
            except IntegrityError:
                raise WorkspaceConflict() from None
            if result is None:
                raise WorkspaceConflict()

    def get_record(
        self, user_id: UUID, database_id: UUID, record_id: UUID
    ) -> DatabaseRecord | None:
        row = self.session.scalar(
            select(DatabaseRecordModel)
            .where(
                DatabaseRecordModel.user_id == user_id,
                DatabaseRecordModel.database_id == database_id,
                DatabaseRecordModel.id == record_id,
            )
            .execution_options(populate_existing=True)
        )
        return record_entity(row) if row else None

    def list_records(
        self, user_id: UUID, database_id: UUID, trashed: bool, limit: int, offset: int
    ) -> list[DatabaseRecord]:
        return [
            record_entity(row)
            for row in self.session.scalars(
                select(DatabaseRecordModel)
                .where(
                    DatabaseRecordModel.user_id == user_id,
                    DatabaseRecordModel.database_id == database_id,
                    DatabaseRecordModel.trashed_at.is_not(None)
                    if trashed
                    else DatabaseRecordModel.trashed_at.is_(None),
                )
                .order_by(DatabaseRecordModel.created_at, DatabaseRecordModel.id)
                .limit(limit)
                .offset(offset)
            )
        ]

    def record_for_page(
        self, user_id: UUID, database_id: UUID, page_id: UUID
    ) -> DatabaseRecord | None:
        row = self.session.scalar(
            select(DatabaseRecordModel).where(
                DatabaseRecordModel.user_id == user_id,
                DatabaseRecordModel.database_id == database_id,
                DatabaseRecordModel.page_id == page_id,
            )
        )
        return record_entity(row) if row else None

    def page_records(
        self, user_id: UUID, page_id: UUID, limit: int, offset: int
    ) -> list[DatabaseRecord]:
        return [
            record_entity(row)
            for row in self.session.scalars(
                select(DatabaseRecordModel)
                .join(
                    DatabaseModel,
                    DatabaseRecordModel.database_id == DatabaseModel.id,
                )
                .where(
                    DatabaseRecordModel.user_id == user_id,
                    DatabaseModel.user_id == user_id,
                    DatabaseRecordModel.page_id == page_id,
                    DatabaseRecordModel.trashed_at.is_(None),
                    DatabaseModel.trashed_at.is_(None),
                )
                .order_by(DatabaseRecordModel.created_at, DatabaseRecordModel.id)
                .limit(limit)
                .offset(offset)
            )
        ]

    def record_count(self, user_id: UUID, database_id: UUID) -> int:
        return (
            self.session.scalar(
                select(func.count())
                .select_from(DatabaseRecordModel)
                .where(
                    DatabaseRecordModel.user_id == user_id,
                    DatabaseRecordModel.database_id == database_id,
                )
            )
            or 0
        )

    def create_record(self, record: DatabaseRecord) -> None:
        self.session.add(DatabaseRecordModel(**asdict(record)))
        self.session.flush()

    def save_record(self, record: DatabaseRecord, expected_version: int) -> None:
        values = asdict(record)
        for field in ("id", "user_id", "database_id", "page_id"):
            values.pop(field)
        result = self.session.scalar(
            update(DatabaseRecordModel)
            .where(
                DatabaseRecordModel.user_id == record.user_id,
                DatabaseRecordModel.database_id == record.database_id,
                DatabaseRecordModel.id == record.id,
                DatabaseRecordModel.version == expected_version,
            )
            .values(**values)
            .returning(DatabaseRecordModel.id)
        )
        if result is None:
            raise WorkspaceConflict()
