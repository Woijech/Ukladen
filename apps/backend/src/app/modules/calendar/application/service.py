from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from app.modules.calendar.application.legacy_service import MAX_PERIOD as MAX_PERIOD
from app.modules.calendar.application.legacy_service import PersonalEventService as PersonalEventService
from app.modules.academics.application.profile import AcademicService
from app.modules.calendar.application.ports import CalendarRepository
from app.modules.calendar.domain.events import (
    PERSONAL_FIELDS,
    CalendarConflict,
    CalendarEventNotFound,
    InvalidCalendarInput,
    PersonalEvent,
    ResolvedEvent,
    ScheduleOverride,
    apply_override,
    date_range,
    overlaps,
    override_values,
    personal_values,
)
from app.modules.schedule.application.queries import ScheduleEventNotFound, ScheduleQueryService
from app.modules.schedule.application.storage import ScheduleState
from app.modules.users.application.ports import ProfileRepository
from app.modules.users.domain.profile import ProfileUnavailable, UserProfile


@dataclass(frozen=True)
class CalendarResult:
    events: list[ResolvedEvent]
    timezone: str
    source: ScheduleState | None
    warnings: list[str]


@dataclass(frozen=True)
class OverrideEntry:
    override: ScheduleOverride
    source_status: Literal["active", "inactive_source", "outside_profile"]


@dataclass(frozen=True)
class CalendarEventReference:
    source: Literal["personal", "official"]
    event_id: UUID
    title: str
    starts_at: datetime
    ends_at: datetime
    source_status: Literal["active", "inactive_source", "outside_profile"]
    hidden: bool = False
    skipped: bool = False


class CalendarService:
    """Resolve stored facts and personal changes; callers own transactions and commit."""

    def __init__(
        self,
        repository: CalendarRepository,
        profiles: ProfileRepository,
        academics: AcademicService,
        schedule: ScheduleQueryService,
        *,
        stale_after_seconds: int = 3600,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.repository = repository
        self.profiles = profiles
        self.academics = academics
        self.schedule = schedule
        self.stale_after_seconds = stale_after_seconds
        self.now = now

    def _profile(self, user_id: UUID, *, write: bool = False) -> UserProfile:
        # ponytail: reuse the active-user lock; finer locks if per-user write throughput matters.
        profile = self.profiles.lock_active(user_id) if write else self.profiles.get_active(user_id)
        if profile is None:
            raise ProfileUnavailable()
        return profile

    def get_calendar(
        self,
        user_id: UUID,
        date_from: date,
        date_to: date,
        *,
        include_hidden: bool = False,
        source: Literal["official", "personal"] | None = None,
    ) -> CalendarResult:
        profile = self._profile(user_id)
        starts_at, ends_at = date_range(date_from, date_to, profile.timezone)
        academic = self.academics.get(user_id)
        events: list[ResolvedEvent] = []
        state = None
        warnings: list[str] = []
        if academic is None:
            warnings.append("academic_profile_not_selected")
        else:
            moved = self.repository.moved_overrides(user_id, starts_at, ends_at)
            official = self.schedule.for_interval(
                academic, starts_at, ends_at, tuple(item.official_event_id for item in moved)
            )
            state = official.source
            overrides = {
                item.official_event_id: item
                for item in self.repository.overrides_for_events(
                    user_id, tuple(item.id for item in official.events)
                )
            }
            for item in official.events:
                event = ResolvedEvent(
                    id=f"official:{item.id}",
                    source="official",
                    source_event_id=item.id,
                    kind=item.kind,
                    title=item.subject or item.subject_full_name or item.note or item.kind,
                    description=item.note,
                    starts_at=item.starts_at,
                    ends_at=item.ends_at,
                    location=", ".join(item.rooms) or None,
                    blocks_time=item.kind != "announcement",
                    group_id=item.group_id,
                    subgroup=item.subgroup,
                    subject=item.subject,
                    subject_full_name=item.subject_full_name,
                    lesson_type=item.lesson_type,
                    note=item.note,
                    rooms=item.rooms,
                    teacher_ids=item.teacher_ids,
                    teacher_names=item.teacher_names,
                )
                if item.id in overrides:
                    event = apply_override(event, overrides[item.id])
                events.append(event)
            if state.status != "ready":
                warnings.append(f"schedule_{state.status}")
            if state.last_success_at is not None and (
                self.now() - state.last_success_at > timedelta(seconds=self.stale_after_seconds)
            ):
                warnings.append("schedule_stale")
        for item in self.repository.personal_events(user_id, starts_at, ends_at):
            events.append(
                ResolvedEvent(
                    id=f"personal:{item.id}",
                    source="personal",
                    source_event_id=item.id,
                    kind="personal",
                    title=item.title,
                    description=item.description,
                    starts_at=item.starts_at,
                    ends_at=item.ends_at,
                    location=item.location,
                    blocks_time=item.blocks_time,
                    version=item.version,
                )
            )
        selected = [
            item
            for item in events
            if overlaps(item, starts_at, ends_at)
            and (include_hidden or not item.hidden)
            and (source is None or item.source == source)
        ]
        selected.sort(key=lambda item: (item.starts_at, item.id))
        return CalendarResult(selected, profile.timezone, state, warnings)

    def create_personal_event(self, user_id: UUID, values: Mapping[str, object]) -> PersonalEvent:
        self._profile(user_id, write=True)
        now = self.now()
        event = PersonalEvent(
            id=uuid4(),
            user_id=user_id,
            version=1,
            created_at=now,
            updated_at=now,
            **personal_values(values),
        )
        self.repository.create_personal(event)
        return event

    def get_personal_event(self, user_id: UUID, event_id: UUID) -> PersonalEvent:
        self._profile(user_id)
        event = self.repository.personal_event(user_id, event_id)
        if event is None:
            raise CalendarEventNotFound()
        return event

    def update_personal_event(
        self, user_id: UUID, event_id: UUID, changes: Mapping[str, object], expected_version: int
    ) -> PersonalEvent:
        self._profile(user_id, write=True)
        if not changes or changes.keys() - PERSONAL_FIELDS:
            raise InvalidCalendarInput()
        event = self.get_personal_event(user_id, event_id)
        if type(expected_version) is not int or expected_version < 1:
            raise InvalidCalendarInput()
        if event.version != expected_version:
            raise CalendarConflict()
        values = {name: getattr(event, name) for name in PERSONAL_FIELDS} | dict(changes)
        updated = replace(
            event, **personal_values(values), version=event.version + 1, updated_at=self.now()
        )
        self.repository.save_personal(updated, expected_version)
        return updated

    def delete_personal_event(self, user_id: UUID, event_id: UUID) -> None:
        self._profile(user_id, write=True)
        if not self.repository.delete_personal(user_id, event_id):
            raise CalendarEventNotFound()

    def list_overrides(
        self, user_id: UUID, limit: int = 100, offset: int = 0
    ) -> list[OverrideEntry]:
        self._profile(user_id)
        if not 1 <= limit <= 200 or not 0 <= offset <= 2**31 - 1:
            raise InvalidCalendarInput()
        entries = self.repository.list_overrides(user_id, limit, offset)
        # These IDs come only from this user's stored references, never arbitrary HTTP input.
        official = {
            item.id: item
            for item in self.schedule.referenced_events(
                tuple(item.official_event_id for item in entries)
            )
        }
        academic = self.academics.get(user_id)
        result: list[OverrideEntry] = []
        for entry in entries:
            event = official.get(entry.official_event_id)
            status: Literal["active", "inactive_source", "outside_profile"] = "active"
            if event is None or not event.active:
                status = "inactive_source"
            elif (
                academic is None
                or event.group_id != academic.group.id
                or (academic.subgroup is not None and event.subgroup not in (0, academic.subgroup))
            ):
                status = "outside_profile"
            result.append(OverrideEntry(entry, status))
        return result

    def set_override(
        self, user_id: UUID, event_id: UUID, values: Mapping[str, object], expected_version: int = 0
    ) -> ScheduleOverride:
        self._profile(user_id, write=True)
        event = self.schedule.event(event_id, self.academics.get(user_id))
        if not event.active:
            raise CalendarConflict()
        if type(expected_version) is not int or expected_version < 0:
            raise InvalidCalendarInput()
        current = self.repository.override(user_id, event_id)
        if (current.version if current else 0) != expected_version:
            raise CalendarConflict()
        now = self.now()
        override = ScheduleOverride(
            user_id=user_id,
            official_event_id=event_id,
            version=expected_version + 1,
            created_at=current.created_at if current else now,
            updated_at=now,
            **override_values(values),
        )
        self.repository.save_override(override, expected_version)
        return override

    def delete_override(self, user_id: UUID, event_id: UUID) -> None:
        self._profile(user_id, write=True)
        if not self.repository.delete_override(user_id, event_id):
            raise CalendarEventNotFound()

    def require_link_target(
        self,
        user_id: UUID,
        source: Literal["personal", "official"],
        event_id: UUID,
    ) -> None:
        """Authorize new links against current ownership or academic group/subgroup."""
        self._profile(user_id)
        if source == "personal":
            self.get_personal_event(user_id, event_id)
            return
        if source != "official":
            raise InvalidCalendarInput()
        academic = self.academics.get(user_id)
        if academic is None:
            raise CalendarEventNotFound()
        try:
            event = self.schedule.event(event_id, academic)
        except ScheduleEventNotFound:
            raise CalendarEventNotFound() from None
        if not event.active:
            raise CalendarConflict()

    def linked_event_references(
        self,
        user_id: UUID,
        references: tuple[tuple[Literal["personal", "official"], UUID], ...],
    ) -> dict[tuple[Literal["personal", "official"], UUID], CalendarEventReference]:
        """Resolve only IDs read from this owner's stored links, including historical sources."""
        self._profile(user_id)
        result: dict[tuple[Literal["personal", "official"], UUID], CalendarEventReference] = {}
        for source, event_id in references:
            if source == "personal":
                personal = self.get_personal_event(user_id, event_id)
                result[(source, event_id)] = CalendarEventReference(
                    source,
                    event_id,
                    personal.title,
                    personal.starts_at,
                    personal.ends_at,
                    "active",
                )
        official_ids = tuple(event_id for source, event_id in references if source == "official")
        if not official_ids:
            return result
        overrides = {
            item.official_event_id: item
            for item in self.repository.overrides_for_events(user_id, official_ids)
        }
        academic = self.academics.get(user_id)
        for event in self.schedule.referenced_events(official_ids):
            status: Literal["active", "inactive_source", "outside_profile"] = "active"
            if not event.active:
                status = "inactive_source"
            elif (
                academic is None
                or event.group_id != academic.group.id
                or (academic.subgroup is not None and event.subgroup not in (0, academic.subgroup))
            ):
                status = "outside_profile"
            override = overrides.get(event.id)
            result[("official", event.id)] = CalendarEventReference(
                "official",
                event.id,
                override.title
                if override and override.title is not None
                else event.subject or event.subject_full_name or event.note or event.kind,
                override.starts_at
                if override and override.starts_at is not None
                else event.starts_at,
                override.ends_at if override and override.ends_at is not None else event.ends_at,
                status,
                bool(override and override.hidden),
                bool(override and override.skipped),
            )
        return result
