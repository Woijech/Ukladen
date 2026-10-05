from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ProfileUnavailable(Exception):
    """The canonical user is missing or inactive."""


class InvalidProfile(ValueError):
    """The supplied profile changes are invalid."""


@dataclass(frozen=True)
class UserProfile:
    id: UUID
    email: str
    email_verified_at: datetime | None
    status: str
    display_name: str | None
    timezone: str
    locale: str
    created_at: datetime
    updated_at: datetime
    avatar_key: str | None = None


def normalize_profile_changes(changes: Mapping[str, object]) -> dict[str, str | None]:
    if not changes or changes.keys() - {"display_name", "timezone", "locale"}:
        raise InvalidProfile("Invalid profile changes.")
    result: dict[str, str | None] = {}
    for field, value in changes.items():
        if field == "display_name" and value is None:
            result[field] = None
            continue
        if not isinstance(value, str):
            raise InvalidProfile("Invalid profile changes.")
        if field == "display_name":
            value = value.strip()
            if not 1 <= len(value) <= 100:
                raise InvalidProfile("Invalid display name.")
        elif field == "timezone":
            try:
                ZoneInfo(value)
            except ZoneInfoNotFoundError, ValueError:
                raise InvalidProfile("Invalid timezone.") from None
        elif value not in {"ru", "en"}:
            raise InvalidProfile("Invalid locale.")
        result[field] = value
    return result
