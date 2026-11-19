from dataclasses import asdict
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.modules.calendar.domain.calendars import CalendarVisibility, PersonalCalendar
from app.modules.calendar.domain.events import CalendarConflict
from app.modules.calendar.infrastructure.orm import (
    CalendarVisibilityModel,
    PersonalCalendarEventModel,
    PersonalCalendarModel,
)


class SqlAlchemyPersonalCalendars:
    def __init__(self, session: Session):
        self.session = session

    def list(self, owner: UUID) -> list[PersonalCalendar]:
        return [
            self.entity(row)
            for row in self.session.scalars(
                select(PersonalCalendarModel)
                .where(PersonalCalendarModel.user_id == owner)
                .order_by(PersonalCalendarModel.created_at, PersonalCalendarModel.id)
            )
        ]

    @staticmethod
    def entity(row: PersonalCalendarModel) -> PersonalCalendar:
        return PersonalCalendar(
            **{key: getattr(row, key) for key in PersonalCalendar.__dataclass_fields__}
        )

    def get(self, owner: UUID, identifier: UUID) -> PersonalCalendar | None:
        row = self.session.scalar(
            select(PersonalCalendarModel)
            .where(PersonalCalendarModel.user_id == owner, PersonalCalendarModel.id == identifier)
            .execution_options(populate_existing=True)
        )
        return self.entity(row) if row else None

    def create(self, calendar: PersonalCalendar) -> None:
        self.session.add(PersonalCalendarModel(**asdict(calendar)))
        self.session.flush()

    def save(self, calendar: PersonalCalendar, version: int) -> None:
        saved = self.session.scalar(
            update(PersonalCalendarModel)
            .where(
                PersonalCalendarModel.user_id == calendar.user_id,
                PersonalCalendarModel.id == calendar.id,
                PersonalCalendarModel.version == version,
            )
            .values(
                name=calendar.name,
                color=calendar.color,
                version=calendar.version,
                updated_at=calendar.updated_at,
            )
            .returning(PersonalCalendarModel.id)
        )
        if saved is None:
            raise CalendarConflict()

    def remove(self, owner: UUID, identifier: UUID, now: datetime) -> None:
        self.session.execute(
            update(PersonalCalendarEventModel)
            .where(
                PersonalCalendarEventModel.user_id == owner,
                PersonalCalendarEventModel.calendar_id == identifier,
            )
            .values(
                calendar_id=None, version=PersonalCalendarEventModel.version + 1, updated_at=now
            )
        )
        row = self.session.get(PersonalCalendarModel, identifier)
        if row is not None and row.user_id == owner:
            self.session.delete(row)
            self.session.flush()

    def visibility(self, owner: UUID) -> CalendarVisibility:
        row = self.session.get(CalendarVisibilityModel, owner, populate_existing=True)
        return (
            CalendarVisibility(
                row.version,
                row.default_visible,
                tuple(UUID(i) for i in row.hidden_calendar_ids),
                tuple(row.hidden_lesson_types),
            )
            if row
            else CalendarVisibility()
        )

    def save_visibility(self, owner: UUID, value: CalendarVisibility) -> None:
        row = self.session.get(CalendarVisibilityModel, owner)
        if row is None:
            row = CalendarVisibilityModel(user_id=owner)
            self.session.add(row)
        row.version, row.default_visible = value.version, value.default_visible
        row.hidden_calendar_ids = [str(i) for i in value.hidden_calendar_ids]
        row.hidden_lesson_types = list(value.hidden_lesson_types)
        self.session.flush()
