from dataclasses import dataclass
from typing import Literal
from uuid import UUID


class InvalidSearchInput(ValueError):
    pass


@dataclass(frozen=True)
class SearchHit:
    source: Literal["page", "material"]
    id: UUID
    title: str
    snippet: str
    score: float
    version: int
    kind: Literal["file", "link"] | None = None


@dataclass(frozen=True)
class SearchQuery:
    text: str
    source: Literal["page", "material"] | None = None
    kind: Literal["file", "link"] | None = None
    extension: Literal["pdf", "docx", "pptx", "txt", "md"] | None = None
    limit: int = 20
    offset: int = 0
    source_ids: tuple[UUID, ...] = ()
