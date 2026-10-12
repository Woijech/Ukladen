from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.notes.domain.blocks import PageDocument, document_markdown


class InvalidPageInput(ValueError):
    pass


class PageNotFound(Exception):
    pass


class PageConflict(Exception):
    pass


def page_title(value: object) -> str:
    if not isinstance(value, str):
        raise InvalidPageInput()
    value = value.strip()
    if not 1 <= len(value) <= 200 or "\x00" in value:
        raise InvalidPageInput()
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise InvalidPageInput() from None
    return value


def page_text(title: object, content: object) -> tuple[str, str]:
    title = page_title(title)
    if not isinstance(content, str) or len(content) > 100000 or "\x00" in content:
        raise InvalidPageInput()
    return title, content


def require_version(actual: int, expected: int) -> None:
    if type(expected) is not int or not 1 <= expected <= 2**31 - 2:
        raise InvalidPageInput()
    if actual != expected:
        raise PageConflict()


@dataclass(frozen=True)
class PageMetadata:
    id: UUID
    user_id: UUID
    parent_id: UUID | None
    title: str
    version: int
    created_at: datetime
    updated_at: datetime
    trashed_at: datetime | None = None
    trash_batch_id: UUID | None = None


@dataclass(frozen=True, kw_only=True)
class Page(PageMetadata):
    document: PageDocument

    @property
    def content(self) -> str:
        """Derived Markdown for the existing page API; document is authoritative."""
        return document_markdown(self.document)
