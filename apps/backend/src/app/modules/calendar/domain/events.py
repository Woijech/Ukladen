from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID


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
            raise ValueError("Event title must not be empty.")

        for value in (
            self.starts_at,
            self.ends_at,
            self.created_at,
            self.updated_at,
        ):
            if value.utcoffset() is None:
                raise ValueError("Event timestamps must be timezone-aware.")

        if self.starts_at.astimezone(UTC) >= self.ends_at.astimezone(UTC):
            raise ValueError("Event end must be after its start.")
