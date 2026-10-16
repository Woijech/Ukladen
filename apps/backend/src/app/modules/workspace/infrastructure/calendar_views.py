from dataclasses import asdict
from typing import cast
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.modules.workspace.domain.calendar_views import (
    CalendarLayout,
    CalendarView,
    SortOrder,
    source_filters,
)
from app.modules.workspace.domain.organization import WorkspaceConflict
from app.modules.workspace.infrastructure.orm import CalendarViewModel


def view_entity(row: CalendarViewModel) -> CalendarView:
    return CalendarView(
        id=row.id,
        user_id=row.user_id,
        name=row.name,
        color=row.color,
        sources=source_filters(row.sources),
        layout=cast(CalendarLayout, row.layout),
        sort_order=cast(SortOrder, row.sort_order),
        include_hidden=row.include_hidden,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def view_columns(view: CalendarView) -> dict[str, object]:
    values = asdict(view)
    values["sources"] = [
        {
            "source": source.source,
            "collection_ids": [str(identifier) for identifier in source.collection_ids],
            "tag_ids": [str(identifier) for identifier in source.tag_ids],
        }
        for source in view.sources
    ]
    return values


class SqlAlchemyCalendarViews:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, user_id: UUID, identifier: UUID) -> CalendarView | None:
        row = self.session.scalar(
            select(CalendarViewModel)
            .where(CalendarViewModel.user_id == user_id, CalendarViewModel.id == identifier)
            .execution_options(populate_existing=True)
        )
        return view_entity(row) if row else None

    def list(self, user_id: UUID, limit: int, offset: int) -> list[CalendarView]:
        return [
            view_entity(row)
            for row in self.session.scalars(
                select(CalendarViewModel)
                .where(CalendarViewModel.user_id == user_id)
                .order_by(CalendarViewModel.created_at, CalendarViewModel.id)
                .limit(limit)
                .offset(offset)
            )
        ]

    def create(self, view: CalendarView) -> None:
        self.session.add(CalendarViewModel(**view_columns(view)))
        self.session.flush()

    def save(self, view: CalendarView, expected_version: int) -> None:
        values = view_columns(view)
        values.pop("id")
        values.pop("user_id")
        identifier = self.session.scalar(
            update(CalendarViewModel)
            .where(
                CalendarViewModel.user_id == view.user_id,
                CalendarViewModel.id == view.id,
                CalendarViewModel.version == expected_version,
            )
            .values(**values)
            .returning(CalendarViewModel.id)
        )
        if identifier is None:
            raise WorkspaceConflict()

    def delete(self, view: CalendarView, expected_version: int) -> None:
        identifier = self.session.scalar(
            delete(CalendarViewModel)
            .where(
                CalendarViewModel.user_id == view.user_id,
                CalendarViewModel.id == view.id,
                CalendarViewModel.version == expected_version,
            )
            .returning(CalendarViewModel.id)
        )
        if identifier is None:
            raise WorkspaceConflict()
