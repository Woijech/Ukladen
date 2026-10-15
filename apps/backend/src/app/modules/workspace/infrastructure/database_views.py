from dataclasses import asdict
from uuid import UUID

from sqlalchemy import bindparam, case, delete, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.modules.workspace.application.database_view_ports import RecordReference
from app.modules.workspace.domain.database_views import (
    DatabaseQuery,
    DatabaseView,
    PropertyFilter,
    parse_query,
    query_value,
)
from app.modules.workspace.domain.databases import DatabaseProperty, DatabaseRecord
from app.modules.workspace.domain.organization import WorkspaceConflict
from app.modules.workspace.infrastructure.database_content import record_entity
from app.modules.workspace.infrastructure.orm import DatabaseRecordModel, DatabaseViewModel


def view_entity(row: DatabaseViewModel) -> DatabaseView:
    return DatabaseView(
        id=row.id,
        user_id=row.user_id,
        database_id=row.database_id,
        name=row.name,
        color=row.color,
        query=parse_query(row.query),
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def view_columns(view: DatabaseView) -> dict[str, object]:
    values: dict[str, object] = asdict(view)
    values["query"] = query_value(view.query)
    return values


def filter_expression(item: PropertyFilter, definition: DatabaseProperty) -> ColumnElement:
    value = DatabaseRecordModel.values[str(item.property_id)]
    missing = value.as_string().is_(None)
    if item.operator in ("is_empty", "is_not_empty"):
        empty = or_(
            missing,
            value == bindparam(None, "", type_=JSONB),
            value == bindparam(None, [], type_=JSONB),
        )
        return ~empty if item.operator == "is_not_empty" else empty
    if item.operator in ("eq", "neq"):
        if item.value is None:
            return ~missing if item.operator == "neq" else missing
        equal = value == bindparam(None, item.value, type_=JSONB)
        return or_(missing, ~equal) if item.operator == "neq" else equal
    if item.operator == "contains":
        if definition.kind == "multi_select":
            return value.contains([item.value])
        assert isinstance(item.value, str)
        return value.as_string().contains(item.value, autoescape=True)
    if definition.kind == "date":
        assert isinstance(item.value, dict)
        target = value["start"].as_string()
        operand = item.value["start"]
        assert isinstance(operand, str)
        kinds_match = value["kind"].as_string() == item.value["kind"]
        comparisons = {
            "gt": target > operand,
            "gte": target >= operand,
            "lt": target < operand,
            "lte": target <= operand,
        }
        return kinds_match & comparisons[item.operator]
    assert isinstance(item.value, (int, float))
    number = value.as_float()
    return {
        "gt": number > item.value,
        "gte": number >= item.value,
        "lt": number < item.value,
        "lte": number <= item.value,
    }[item.operator]


def sort_expression(definition: DatabaseProperty) -> ColumnElement:
    value = DatabaseRecordModel.values[str(definition.id)]
    if definition.kind == "number":
        return value.as_float()
    if definition.kind == "checkbox":
        return value.as_boolean()
    if definition.kind == "date":
        return value["start"].as_string()
    if definition.kind == "select" and definition.options:
        return case(
            *[
                (value.as_string() == str(option.id), index)
                for index, option in enumerate(definition.options)
            ],
            else_=None,
        )
    return value.as_string()


class SqlAlchemyDatabaseViews:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, user_id: UUID, database_id: UUID, view_id: UUID) -> DatabaseView | None:
        row = self.session.scalar(
            select(DatabaseViewModel)
            .where(
                DatabaseViewModel.user_id == user_id,
                DatabaseViewModel.database_id == database_id,
                DatabaseViewModel.id == view_id,
            )
            .execution_options(populate_existing=True)
        )
        return view_entity(row) if row else None

    def list(self, user_id: UUID, database_id: UUID, limit: int, offset: int) -> list[DatabaseView]:
        return [
            view_entity(row)
            for row in self.session.scalars(
                select(DatabaseViewModel)
                .where(
                    DatabaseViewModel.user_id == user_id,
                    DatabaseViewModel.database_id == database_id,
                )
                .order_by(DatabaseViewModel.created_at, DatabaseViewModel.id)
                .limit(limit)
                .offset(offset)
            )
        ]

    def create(self, view: DatabaseView) -> None:
        self.session.add(DatabaseViewModel(**view_columns(view)))
        self.session.flush()

    def save(self, view: DatabaseView, expected_version: int) -> None:
        values = view_columns(view)
        for field in ("id", "user_id", "database_id"):
            values.pop(field)
        result = self.session.scalar(
            update(DatabaseViewModel)
            .where(
                DatabaseViewModel.user_id == view.user_id,
                DatabaseViewModel.database_id == view.database_id,
                DatabaseViewModel.id == view.id,
                DatabaseViewModel.version == expected_version,
            )
            .values(**values)
            .returning(DatabaseViewModel.id)
        )
        if result is None:
            raise WorkspaceConflict()

    def delete(self, view: DatabaseView, expected_version: int) -> None:
        result = self.session.scalar(
            delete(DatabaseViewModel)
            .where(
                DatabaseViewModel.user_id == view.user_id,
                DatabaseViewModel.database_id == view.database_id,
                DatabaseViewModel.id == view.id,
                DatabaseViewModel.version == expected_version,
            )
            .returning(DatabaseViewModel.id)
        )
        if result is None:
            raise WorkspaceConflict()

    def candidates(
        self,
        user_id: UUID,
        database_id: UUID,
        query: DatabaseQuery,
        definitions: list[DatabaseProperty],
    ) -> list[RecordReference]:
        properties = {item.id: item for item in definitions}
        statement = select(DatabaseRecordModel.id, DatabaseRecordModel.page_id).where(
            DatabaseRecordModel.user_id == user_id,
            DatabaseRecordModel.database_id == database_id,
            DatabaseRecordModel.trashed_at.is_(None),
        )
        for item in query.filters:
            statement = statement.where(filter_expression(item, properties[item.property_id]))
        for sort in query.sorts:
            expression = sort_expression(properties[sort.property_id])
            statement = statement.order_by(
                (expression.desc() if sort.direction == "desc" else expression.asc()).nulls_last()
            )
        statement = statement.order_by(
            DatabaseRecordModel.created_at, DatabaseRecordModel.id
        ).limit(10001)
        return [
            RecordReference(identifier, page_id)
            for identifier, page_id in self.session.execute(statement)
        ]

    def records(
        self, user_id: UUID, database_id: UUID, record_ids: tuple[UUID, ...]
    ) -> list[DatabaseRecord]:
        return [
            record_entity(row)
            for row in self.session.scalars(
                select(DatabaseRecordModel).where(
                    DatabaseRecordModel.user_id == user_id,
                    DatabaseRecordModel.database_id == database_id,
                    DatabaseRecordModel.id.in_(record_ids),
                )
            )
        ]
