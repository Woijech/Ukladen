from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.notes.domain.blocks import PageDocument


@dataclass(frozen=True)
class PageRevisionSummary:
    page_id: UUID
    version: int
    title: str
    saved_at: datetime


@dataclass(frozen=True)
class PageRevision(PageRevisionSummary):
    document: PageDocument
