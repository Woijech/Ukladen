import re
from dataclasses import replace
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from app.modules.calendar.domain.calendars import CalendarVisibility, PersonalCalendar
from app.modules.calendar.domain.events import (
    CalendarConflict,
    CalendarEventNotFound,
    InvalidCalendarInput,
)
from app.modules.users.application.ports import ProfileRepository
from app.modules.users.domain.profile import ProfileUnavailable


class PersonalCalendarRepository(Protocol):
    def list(self, owner: UUID) -> list[PersonalCalendar]: ...
    def get(self, owner: UUID, identifier: UUID) -> PersonalCalendar | None: ...
    def create(self, calendar: PersonalCalendar) -> None: ...
    def save(self, calendar: PersonalCalendar, version: int) -> None: ...
    def remove(self, owner: UUID, identifier: UUID, now: datetime) -> None: ...
    def visibility(self, owner: UUID) -> CalendarVisibility: ...
    def save_visibility(self, owner: UUID, value: CalendarVisibility) -> None: ...


class PersonalCalendarService:
    def __init__(self, repository: PersonalCalendarRepository, profiles: ProfileRepository):
        self.repository, self.profiles = repository, profiles

    def require_user(self, owner: UUID, *, write: bool = False) -> None:
        if not (self.profiles.lock_active(owner) if write else self.profiles.get_active(owner)):
            raise ProfileUnavailable()

    def list(self, owner: UUID) -> list[PersonalCalendar]:
        self.require_user(owner)
        return self.repository.list(owner)

    def get(self, owner: UUID, identifier: UUID) -> PersonalCalendar:
        self.require_user(owner)
        calendar = self.repository.get(owner, identifier)
        if calendar is None:
            raise CalendarEventNotFound()
        return calendar

    def write(
        self,
        owner: UUID,
        name: str,
        color: str,
        identifier: UUID | None = None,
        expected_version: int = 0,
    ) -> PersonalCalendar:
        self.require_user(owner, write=True)
        name = name.strip()
        try:
            name.encode("utf-8")
        except UnicodeEncodeError:
            raise InvalidCalendarInput() from None
        if (
            not 1 <= len(name) <= 100
            or any(ord(c) < 32 or ord(c) == 127 for c in name)
            or not re.fullmatch(r"#[0-9a-fA-F]{6}", color)
        ):
            raise InvalidCalendarInput()
        now = datetime.now(UTC)
        if identifier is None:
            if len(self.repository.list(owner)) >= 100:
                raise InvalidCalendarInput()
            value = PersonalCalendar(
                id=uuid4(),
                user_id=owner,
                name=name,
                color=color.lower(),
                version=1,
                created_at=now,
                updated_at=now,
            )
            self.repository.create(value)
        else:
            current = self.get(owner, identifier)
            if type(expected_version) is not int or current.version != expected_version:
                raise CalendarConflict()
            value = replace(
                current, name=name, color=color.lower(), version=current.version + 1, updated_at=now
            )
            self.repository.save(value, expected_version)
        return value

    def delete(self, owner: UUID, identifier: UUID, expected_version: int) -> None:
        self.require_user(owner, write=True)
        current = self.get(owner, identifier)
        if type(expected_version) is not int or current.version != expected_version:
            raise CalendarConflict()
        self.repository.remove(owner, identifier, datetime.now(UTC))
        visibility = self.repository.visibility(owner)
        if identifier in visibility.hidden_calendar_ids:
            self.repository.save_visibility(
                owner,
                replace(
                    visibility,
                    version=visibility.version + 1,
                    hidden_calendar_ids=tuple(
                        i for i in visibility.hidden_calendar_ids if i != identifier
                    ),
                ),
            )

    def visibility(self, owner: UUID) -> CalendarVisibility:
        self.require_user(owner)
        return self.repository.visibility(owner)

    def set_visibility(self, owner: UUID, value: CalendarVisibility) -> CalendarVisibility:
        self.require_user(owner, write=True)
        current = self.repository.visibility(owner)
        if type(value.version) is not int or current.version != value.version:
            raise CalendarConflict()
        if (
            type(value.default_visible) is not bool
            or len(value.hidden_calendar_ids) > 100
            or not set(value.hidden_lesson_types) <= {"ЛК", "ЛР", "ПЗ", "other"}
        ):
            raise InvalidCalendarInput()
        for identifier in value.hidden_calendar_ids:
            self.get(owner, identifier)
        updated = replace(value, version=current.version + 1)
        self.repository.save_visibility(owner, updated)
        return updated
