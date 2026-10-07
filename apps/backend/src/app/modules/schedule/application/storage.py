from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from app.modules.schedule.application.provider import Schedule
from app.modules.schedule.domain.events import OfficialEvent

SyncState = Literal["not_synced", "syncing", "ready", "unpublished", "error", "unsupported"]


@dataclass(frozen=True)
class ScheduleState:
    group_id: int
    group_number: str
    status: SyncState = "not_synced"
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    error_code: str | None = None


class ScheduleStore(Protocol):
    """Atomic storage operations; external requests never run inside these transactions."""

    def claim(
        self, group_id: int, group_number: str, now: datetime, *, force: bool = False
    ) -> UUID | None: ...
    def apply(
        self,
        group_id: int,
        token: UUID,
        snapshot: Schedule | None,
        events: list[OfficialEvent],
        now: datetime,
    ) -> bool: ...
    def fail(self, group_id: int, token: UUID, code: str, now: datetime) -> None: ...
    def state(self, group_id: int, group_number: str) -> ScheduleState: ...
    def group_id(self, group_number: str) -> int | None: ...
    def events(
        self, group_id: int, starts_at: datetime, ends_at: datetime, subgroup: int | None
    ) -> list[OfficialEvent]: ...
    def read(
        self,
        group_id: int,
        group_number: str,
        starts_at: datetime,
        ends_at: datetime,
        subgroup: int | None,
        event_ids: tuple[UUID, ...] = (),
    ) -> tuple[ScheduleState, list[OfficialEvent]]: ...
    def event(self, event_id: UUID) -> OfficialEvent | None: ...
    def by_ids(self, event_ids: tuple[UUID, ...]) -> list[OfficialEvent]: ...
