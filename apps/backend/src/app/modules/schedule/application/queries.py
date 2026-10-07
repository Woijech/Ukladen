from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from app.modules.academics.domain.profile import AcademicProfile
from app.modules.schedule.application.schedule import AcademicProfileRequired
from app.modules.schedule.application.storage import ScheduleState, ScheduleStore
from app.modules.schedule.domain.events import InvalidScheduleRange, OfficialEvent, date_interval


class ScheduleEventNotFound(Exception):
    pass


@dataclass(frozen=True)
class ScheduleEvents:
    events: list[OfficialEvent]
    source: ScheduleState


def require_profile(profile: AcademicProfile | None) -> AcademicProfile:
    if profile is None:
        raise AcademicProfileRequired()
    return profile


class ScheduleQueryService:
    def __init__(self, store: ScheduleStore) -> None:
        self.store = store

    def for_profile(
        self, profile: AcademicProfile | None, date_from: date, date_to: date
    ) -> ScheduleEvents:
        selected = require_profile(profile)
        starts_at, ends_at = date_interval(date_from, date_to)
        source, events = self.store.read(
            selected.group.id, selected.group.name, starts_at, ends_at, selected.subgroup
        )
        return ScheduleEvents(events, source)

    def for_interval(
        self,
        profile: AcademicProfile | None,
        starts_at: datetime,
        ends_at: datetime,
        event_ids: tuple[UUID, ...] = (),
    ) -> ScheduleEvents:
        """Read exact instants plus moved occurrences, filtered by academic context."""
        selected = require_profile(profile)
        if starts_at.utcoffset() is None or ends_at.utcoffset() is None:
            raise InvalidScheduleRange()
        try:
            starts_at, ends_at = starts_at.astimezone(UTC), ends_at.astimezone(UTC)
        except ValueError, OverflowError:
            raise InvalidScheduleRange() from None
        if ends_at <= starts_at or ends_at - starts_at > timedelta(days=368):
            raise InvalidScheduleRange()
        source, events = self.store.read(
            selected.group.id, selected.group.name, starts_at, ends_at, selected.subgroup, event_ids
        )
        return ScheduleEvents(events, source)

    def referenced_events(self, event_ids: tuple[UUID, ...]) -> list[OfficialEvent]:
        """Read historical facts only for IDs obtained from caller-owned stored references."""
        return self.store.by_ids(event_ids)

    def for_group(
        self, group_number: str, date_from: date, date_to: date, subgroup: int | None = None
    ) -> ScheduleEvents:
        starts_at, ends_at = date_interval(date_from, date_to)
        group_id = self.store.group_id(group_number)
        if group_id is None:
            raise ScheduleEventNotFound()
        source, events = self.store.read(group_id, group_number, starts_at, ends_at, subgroup)
        return ScheduleEvents(events, source)

    def event(self, event_id: UUID, profile: AcademicProfile | None) -> OfficialEvent:
        selected = require_profile(profile)
        event = self.store.event(event_id)
        if event is None or event.group_id != selected.group.id:
            raise ScheduleEventNotFound()
        if selected.subgroup is not None and event.subgroup not in (0, selected.subgroup):
            raise ScheduleEventNotFound()
        return event

    def state(self, profile: AcademicProfile | None) -> ScheduleState:
        selected = require_profile(profile)
        return self.store.state(selected.group.id, selected.group.name)
