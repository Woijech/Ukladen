from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.orm import Session

from app.modules.calendar.domain.events import PersonalCalendarEvent
from app.modules.calendar.infrastructure.orm import PersonalCalendarEventModel


class SqlAlchemyPersonalCalendarEventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, user_id: UUID, event: PersonalCalendarEvent) -> PersonalCalendarEvent:
        self._require_owner(user_id, event)
        values = asdict(event)
        values["blocks_time"] = values.pop("is_busy")
        row = self.session.scalars(
            insert(PersonalCalendarEventModel)
            .values(**values)
            .returning(PersonalCalendarEventModel)
        ).one()
        return self._to_event(row)

    def get(self, user_id: UUID, event_id: UUID) -> PersonalCalendarEvent | None:
        row = self.session.scalar(
            select(PersonalCalendarEventModel)
            .where(
                PersonalCalendarEventModel.user_id == user_id,
                PersonalCalendarEventModel.id == event_id,
            )
            .execution_options(populate_existing=True)
        )
        return self._to_event(row) if row is not None else None

    def list_for_period(
        self, user_id: UUID, starts_at: datetime, ends_at: datetime
    ) -> list[PersonalCalendarEvent]:
        if starts_at.utcoffset() is None or ends_at.utcoffset() is None:
            raise ValueError("Period timestamps must be timezone-aware.")
        starts_at, ends_at = starts_at.astimezone(UTC), ends_at.astimezone(UTC)
        if starts_at >= ends_at:
            raise ValueError("Period end must be after its start.")
        rows = self.session.scalars(
            select(PersonalCalendarEventModel)
            .where(
                PersonalCalendarEventModel.user_id == user_id,
                PersonalCalendarEventModel.starts_at < ends_at,
                PersonalCalendarEventModel.ends_at > starts_at,
            )
            .order_by(PersonalCalendarEventModel.starts_at, PersonalCalendarEventModel.id)
            .execution_options(populate_existing=True)
        )
        return [self._to_event(row) for row in rows]

    def update(self, user_id: UUID, event: PersonalCalendarEvent) -> PersonalCalendarEvent | None:
        self._require_owner(user_id, event)
        row = self.session.scalar(
            update(PersonalCalendarEventModel)
            .where(
                PersonalCalendarEventModel.user_id == user_id,
                PersonalCalendarEventModel.id == event.id,
            )
            .values(
                title=event.title,
                description=event.description,
                starts_at=event.starts_at,
                ends_at=event.ends_at,
                blocks_time=event.is_busy,
                version=PersonalCalendarEventModel.version + 1,
                updated_at=func.clock_timestamp(),
            )
            .returning(PersonalCalendarEventModel)
            .execution_options(populate_existing=True)
        )
        return self._to_event(row) if row is not None else None

    def delete(self, user_id: UUID, event_id: UUID) -> bool:
        return (
            self.session.scalar(
                delete(PersonalCalendarEventModel)
                .where(
                    PersonalCalendarEventModel.user_id == user_id,
                    PersonalCalendarEventModel.id == event_id,
                )
                .returning(PersonalCalendarEventModel.id)
            )
            is not None
        )

    @staticmethod
    def _require_owner(user_id: UUID, event: PersonalCalendarEvent) -> None:
        if event.user_id != user_id:
            raise ValueError("Event owner must match the requested user.")

    @staticmethod
    def _to_event(row: PersonalCalendarEventModel) -> PersonalCalendarEvent:
        return PersonalCalendarEvent(
            id=row.id,
            user_id=row.user_id,
            title=row.title,
            description=row.description,
            starts_at=row.starts_at.astimezone(UTC),
            ends_at=row.ends_at.astimezone(UTC),
            is_busy=row.is_busy,
            created_at=row.created_at.astimezone(UTC),
            updated_at=row.updated_at.astimezone(UTC),
        )
