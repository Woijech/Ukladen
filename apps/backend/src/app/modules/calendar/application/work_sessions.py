from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class WorkSessionBusy:
    id: str
    source_event_id: UUID
    title: str
    starts_at: datetime
    ends_at: datetime
    version: int
    source: str = "task_session"
    blocks_time: bool = True


class WorkSessionQuery(Protocol):
    def busy(
        self, user_id: UUID, starts_at: datetime, ends_at: datetime
    ) -> list[WorkSessionBusy]: ...
