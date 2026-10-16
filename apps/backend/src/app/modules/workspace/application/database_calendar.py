from dataclasses import replace
from datetime import date
from uuid import UUID

from app.modules.calendar.application.record_dates import RecordDateProjection
from app.modules.calendar.domain.events import date_range
from app.modules.workspace.application.database_content import RecordResult
from app.modules.workspace.application.database_views import DatabaseViewService
from app.modules.workspace.domain.database_views import (
    query_value,
    validate_binding,
    validate_query,
)
from app.modules.workspace.domain.organization import (
    InvalidWorkspaceInput,
    WorkspaceConflict,
    WorkspaceNotFound,
)
from app.modules.workspace.domain.properties import date_value


class DatabaseCalendarService:
    def __init__(self, views: DatabaseViewService) -> None:
        self.views = views

    def entries(
        self, user_id: UUID, view_id: UUID, date_from: date, date_to: date, timezone: str
    ) -> list[RecordDateProjection]:
        starts_at, ends_at = date_range(date_from, date_to, timezone)
        view = self.views.repository.get_owned(user_id, view_id)
        if view is None:
            raise WorkspaceNotFound()
        database, definitions = self.views.content.schema(user_id, view.database_id)
        try:
            if view.layout != "calendar":
                raise InvalidWorkspaceInput()
            validate_binding(view.layout, view.date_property_id, view.calendar_layout, definitions)
            query = validate_query(query_value(view.query), definitions)
        except InvalidWorkspaceInput:
            raise WorkspaceConflict() from None
        assert view.date_property_id is not None
        candidates = self.views.repository.dates(
            user_id, replace(view, query=query), definitions, date_from, date_to, starts_at, ends_at
        )
        if len(candidates) > 10000:
            raise WorkspaceConflict()
        pages = self.views.notes.summaries(user_id, tuple(item.page_id for item in candidates))
        return [
            RecordDateProjection(
                id=f"record_date:{item.id}:{view.date_property_id}",
                database_id=database.id,
                record_id=item.id,
                page_id=item.page_id,
                property_id=view.date_property_id,
                title=pages[item.page_id].title,
                date=date_value(item.value),
                record_version=item.version,
                schema_version=database.schema_version,
            )
            for item in candidates
            if item.page_id in pages and pages[item.page_id].trashed_at is None
        ]

    def move(
        self,
        user_id: UUID,
        database_id: UUID,
        view_id: UUID,
        record_id: UUID,
        property_id: UUID,
        expected_version: int,
        expected_schema_version: int,
        value: object,
    ) -> RecordResult:
        _, definitions = self.views.content.schema(
            user_id, database_id, expected_schema_version=expected_schema_version, write=True
        )
        view = self.views.get(user_id, database_id, view_id)
        try:
            validate_binding(view.layout, view.date_property_id, view.calendar_layout, definitions)
        except InvalidWorkspaceInput:
            raise WorkspaceConflict() from None
        if view.layout != "calendar" or view.date_property_id != property_id:
            raise WorkspaceConflict()
        return self.views.content.update_record(
            user_id,
            database_id,
            record_id,
            expected_version,
            expected_schema_version,
            {str(property_id): date_value(value)},
        )
