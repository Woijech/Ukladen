from dataclasses import asdict, fields
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.calendar.domain.events import CalendarConflict, PersonalEvent, ScheduleOverride
from app.modules.calendar.infrastructure.legacy_repository import (
    SqlAlchemyPersonalCalendarEventRepository as SqlAlchemyPersonalCalendarEventRepository,
)
from app.modules.calendar.infrastructure.orm import (
    PersonalCalendarEventModel,
    ScheduleOverrideModel,
)


def personal_entity(row: PersonalCalendarEventModel) -> PersonalEvent:
    return PersonalEvent(
        **{field.name: getattr(row, field.name) for field in fields(PersonalEvent)}
    )


def override_entity(row: ScheduleOverrideModel) -> ScheduleOverride:
    return ScheduleOverride(
        **{field.name: getattr(row, field.name) for field in fields(ScheduleOverride)}
    )


class SqlAlchemyCalendarRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def personal_events(
        self, user_id: UUID, starts_at: datetime, ends_at: datetime
    ) -> list[PersonalEvent]:
        return [
            personal_entity(row)
            for row in self.session.scalars(
                select(PersonalCalendarEventModel)
                .where(
                    PersonalCalendarEventModel.user_id == user_id,
                    PersonalCalendarEventModel.starts_at < ends_at,
                    PersonalCalendarEventModel.ends_at > starts_at,
                )
                .order_by(PersonalCalendarEventModel.starts_at, PersonalCalendarEventModel.id)
            )
        ]

    def personal_event(self, user_id: UUID, event_id: UUID) -> PersonalEvent | None:
        row = self.session.scalar(
            select(PersonalCalendarEventModel)
            .where(
                PersonalCalendarEventModel.user_id == user_id,
                PersonalCalendarEventModel.id == event_id,
            )
            .execution_options(populate_existing=True)
        )
        return personal_entity(row) if row is not None else None

    def create_personal(self, event: PersonalEvent) -> None:
        self.session.add(PersonalCalendarEventModel(**asdict(event)))
        self.session.flush()

    def save_personal(self, event: PersonalEvent, expected_version: int) -> None:
        values = asdict(event)
        for field in ("id", "user_id", "created_at"):
            values.pop(field)
        saved = self.session.scalar(
            update(PersonalCalendarEventModel)
            .where(
                PersonalCalendarEventModel.id == event.id,
                PersonalCalendarEventModel.user_id == event.user_id,
                PersonalCalendarEventModel.version == expected_version,
            )
            .values(**values)
            .returning(PersonalCalendarEventModel.id)
        )
        if saved is None:
            raise CalendarConflict()

    def delete_personal(self, user_id: UUID, event_id: UUID) -> bool:
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

    def moved_overrides(
        self, user_id: UUID, starts_at: datetime, ends_at: datetime
    ) -> list[ScheduleOverride]:
        return [
            override_entity(row)
            for row in self.session.scalars(
                select(ScheduleOverrideModel).where(
                    ScheduleOverrideModel.user_id == user_id,
                    ScheduleOverrideModel.starts_at < ends_at,
                    ScheduleOverrideModel.ends_at > starts_at,
                )
            )
        ]

    def overrides_for_events(
        self, user_id: UUID, event_ids: tuple[UUID, ...]
    ) -> list[ScheduleOverride]:
        if not event_ids:
            return []
        return [
            override_entity(row)
            for row in self.session.scalars(
                select(ScheduleOverrideModel).where(
                    ScheduleOverrideModel.user_id == user_id,
                    ScheduleOverrideModel.official_event_id.in_(event_ids),
                )
            )
        ]

    def list_overrides(self, user_id: UUID, limit: int, offset: int) -> list[ScheduleOverride]:
        return [
            override_entity(row)
            for row in self.session.scalars(
                select(ScheduleOverrideModel)
                .where(ScheduleOverrideModel.user_id == user_id)
                .order_by(
                    ScheduleOverrideModel.created_at.desc(), ScheduleOverrideModel.official_event_id
                )
                .limit(limit)
                .offset(offset)
            )
        ]

    def override(self, user_id: UUID, event_id: UUID) -> ScheduleOverride | None:
        row = self.session.scalar(
            select(ScheduleOverrideModel)
            .where(
                ScheduleOverrideModel.user_id == user_id,
                ScheduleOverrideModel.official_event_id == event_id,
            )
            .execution_options(populate_existing=True)
        )
        return override_entity(row) if row is not None else None

    def save_override(self, override: ScheduleOverride, expected_version: int) -> None:
        values = asdict(override)
        if expected_version == 0:
            saved = self.session.scalar(
                insert(ScheduleOverrideModel)
                .values(**values)
                .on_conflict_do_nothing(
                    index_elements=[
                        ScheduleOverrideModel.user_id,
                        ScheduleOverrideModel.official_event_id,
                    ]
                )
                .returning(ScheduleOverrideModel.official_event_id)
            )
        else:
            for field in ("user_id", "official_event_id", "created_at"):
                values.pop(field)
            saved = self.session.scalar(
                update(ScheduleOverrideModel)
                .where(
                    ScheduleOverrideModel.user_id == override.user_id,
                    ScheduleOverrideModel.official_event_id == override.official_event_id,
                    ScheduleOverrideModel.version == expected_version,
                )
                .values(**values)
                .returning(ScheduleOverrideModel.official_event_id)
            )
        if saved is None:
            raise CalendarConflict()

    def delete_override(self, user_id: UUID, event_id: UUID) -> bool:
        return (
            self.session.scalar(
                delete(ScheduleOverrideModel)
                .where(
                    ScheduleOverrideModel.user_id == user_id,
                    ScheduleOverrideModel.official_event_id == event_id,
                )
                .returning(ScheduleOverrideModel.official_event_id)
            )
            is not None
        )
