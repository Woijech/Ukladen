from dataclasses import dataclass
from datetime import date
from typing import Literal
from uuid import UUID

from app.modules.calendar.application.record_dates import RecordCalendarQuery, RecordDateProjection
from app.modules.calendar.application.service import CalendarService
from app.modules.calendar.domain.events import InvalidCalendarInput, ResolvedEvent
from app.modules.schedule.application.storage import ScheduleState


@dataclass(frozen=True)
class CalendarDisplay:
    entries: list[ResolvedEvent | RecordDateProjection]
    timezone: str
    source: ScheduleState | None
    warnings: list[str]


class CalendarCompositionService:
    def __init__(self, calendar: CalendarService, records: RecordCalendarQuery) -> None:
        self.calendar, self.records = calendar, records

    def display(
        self,
        user_id: UUID,
        date_from: date,
        date_to: date,
        database_view_ids: tuple[UUID, ...] = (),
        *,
        include_hidden: bool = False,
        source: Literal["official", "personal"] | None = None,
    ) -> CalendarDisplay:
        if len(database_view_ids) > 20 or len(set(database_view_ids)) != len(database_view_ids):
            raise InvalidCalendarInput()
        result = self.calendar.get_calendar(
            user_id, date_from, date_to, include_hidden=include_hidden, source=source
        )
        projections: dict[str, RecordDateProjection] = {}
        for identifier in database_view_ids:
            projections.update(
                {
                    item.id: item
                    for item in self.records.entries(
                        user_id, identifier, date_from, date_to, result.timezone
                    )
                }
            )
            if len(projections) > 10000:
                raise InvalidCalendarInput()
        return CalendarDisplay(
            [*result.events, *projections.values()], result.timezone, result.source, result.warnings
        )
