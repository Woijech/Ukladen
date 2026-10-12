from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


class InvalidPageInput(ValueError):
    pass


class PageNotFound(Exception):
    pass


class PageConflict(Exception):
    pass


def page_text(title: object, content: object) -> tuple[str, str]:
    if not isinstance(title, str) or not isinstance(content, str):
        raise InvalidPageInput()
    title = title.strip()
    if not 1 <= len(title) <= 200 or len(content) > 100000 or "\x00" in title + content:
        raise InvalidPageInput()
    return title, content


def require_version(actual: int, expected: int) -> None:
    if type(expected) is not int or not 1 <= expected <= 2**31 - 2:
        raise InvalidPageInput()
    if actual != expected:
        raise PageConflict()


@dataclass(frozen=True)
class Page:
    id: UUID
    user_id: UUID
    parent_id: UUID | None
    title: str
    content: str
    version: int
    created_at: datetime
    updated_at: datetime
    trashed_at: datetime | None = None
    trash_batch_id: UUID | None = None
