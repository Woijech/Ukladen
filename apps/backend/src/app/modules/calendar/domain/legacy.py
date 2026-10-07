from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from app.modules.calendar.domain.errors import InvalidEventInput

TITLE_MAX_LENGTH = 200
DESCRIPTION_MAX_LENGTH = 4000
EDITABLE_FIELDS = ("title", "description", "starts_at", "ends_at", "is_busy")
REQUIRED_FIELDS = ("title", "starts_at", "ends_at")


@dataclass(frozen=True)
class PersonalCalendarEvent:
    id: UUID
    user_id: UUID
    title: str
    description: str | None
    starts_at: datetime
    ends_at: datetime
    is_busy: bool
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise InvalidEventInput("Event title must not be empty.")
        if len(self.title) > TITLE_MAX_LENGTH:
            raise InvalidEventInput("Event title is too long.")
        if self.description is not None and len(self.description) > DESCRIPTION_MAX_LENGTH:
            raise InvalidEventInput("Event description is too long.")

        for value in (
            self.starts_at,
            self.ends_at,
            self.created_at,
            self.updated_at,
        ):
            if value.utcoffset() is None:
                raise InvalidEventInput("Event timestamps must be timezone-aware.")

        if self.starts_at.astimezone(UTC) >= self.ends_at.astimezone(UTC):
            raise InvalidEventInput("Event end must be after its start.")


def normalize_event_changes(changes: Mapping[str, object]) -> dict[str, object]:
    """Validate editable fields and return only the supplied, normalized ones.

    Unknown fields and an empty mapping are rejected before any persistence, so a
    partial update never silently clears an omitted field.
    """
    if not changes:
        raise InvalidEventInput("Event changes must not be empty.")
    if changes.keys() - set(EDITABLE_FIELDS):
        raise InvalidEventInput("Event contains unsupported fields.")

    normalized: dict[str, object] = {}
    for field in EDITABLE_FIELDS:
        if field not in changes:
            continue
        value = changes[field]
        if field == "title":
            normalized[field] = _normalize_title(value)
        elif field == "description":
            normalized[field] = _normalize_description(value)
        elif field == "is_busy":
            normalized[field] = _normalize_busy(value)
        else:
            normalized[field] = _normalize_timestamp(field, value)
    return normalized


def normalize_event_data(values: Mapping[str, object]) -> dict[str, object]:
    """Validate a complete event definition; title, start and end are required."""
    normalized = normalize_event_changes(values)
    for field in REQUIRED_FIELDS:
        if field not in normalized:
            raise InvalidEventInput(f"Event requires {field}.")
    return normalized


def new_personal_event(
    user_id: UUID, values: Mapping[str, object], *, now: datetime
) -> PersonalCalendarEvent:
    """Build a validated event owned by user_id from complete input values."""
    data = normalize_event_data(values)
    return PersonalCalendarEvent(
        id=uuid4(),
        user_id=user_id,
        title=cast(str, data["title"]),
        description=cast("str | None", data.get("description")),
        starts_at=cast(datetime, data["starts_at"]),
        ends_at=cast(datetime, data["ends_at"]),
        is_busy=cast(bool, data.get("is_busy", True)),
        created_at=now,
        updated_at=now,
    )


def apply_event_changes(
    event: PersonalCalendarEvent, changes: Mapping[str, object]
) -> PersonalCalendarEvent:
    """Return a copy of event with normalized changes applied and re-validated."""
    return replace(event, **normalize_event_changes(changes))


def _normalize_title(value: object) -> str:
    if not isinstance(value, str):
        raise InvalidEventInput("Event title must be a string.")
    title = value.strip()
    if not title:
        raise InvalidEventInput("Event title must not be empty.")
    if len(title) > TITLE_MAX_LENGTH:
        raise InvalidEventInput("Event title is too long.")
    return title


def _normalize_description(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidEventInput("Event description must be a string.")
    description = value.strip()
    if not description:
        return None
    if len(description) > DESCRIPTION_MAX_LENGTH:
        raise InvalidEventInput("Event description is too long.")
    return description


def _normalize_busy(value: object) -> bool:
    if not isinstance(value, bool):
        raise InvalidEventInput("Event busy flag must be a boolean.")
    return value


def _normalize_timestamp(field: str, value: object) -> datetime:
    if not isinstance(value, datetime):
        raise InvalidEventInput(f"Event {field} must be a timestamp.")
    if value.utcoffset() is None:
        raise InvalidEventInput("Event timestamps must be timezone-aware.")
    return value
