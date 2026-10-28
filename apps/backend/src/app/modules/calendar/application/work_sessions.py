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
    task_id: UUID | None = None
    pinned: bool = False
    source: str = "task_session"
    blocks_time: bool = True


class WorkSessionQuery(Protocol):
    def busy(
        self, user_id: UUID, starts_at: datetime, ends_at: datetime
    ) -> list[WorkSessionBusy]: ...


@dataclass(frozen=True)
class TaskDeadline:
    task_id: UUID
    title: str
    deadline_at: datetime
    version: int
    blocks_time: bool = False
