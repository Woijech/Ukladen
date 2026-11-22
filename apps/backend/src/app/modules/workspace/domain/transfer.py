"""Portable personal page/database snapshots, independent of transport frameworks."""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_PAGES = 1000
MAX_DATABASES = 100
MAX_RECORDS = 10000
MAX_VIEWS = 1000


@dataclass(frozen=True, kw_only=True)
class PageSnapshot:
    id: UUID
    parent_id: UUID | None
    title: str
    document: dict[str, object]
    trash_batch_id: UUID | None


@dataclass(frozen=True, kw_only=True)
class PropertySnapshot:
    id: UUID
    name: str
    kind: str
    options: tuple[dict[str, str], ...]
    relation_database_id: UUID | None
    calculation: dict[str, str]
    position: int
    trashed: bool


@dataclass(frozen=True, kw_only=True)
class RecordSnapshot:
    id: UUID
    page_id: UUID
    values: dict[str, object]
    trashed: bool


@dataclass(frozen=True, kw_only=True)
class ViewSnapshot:
    id: UUID
    name: str
    color: str | None
    query: dict[str, object]
    layout: Literal["table", "calendar", "list", "board"]
    date_property_id: UUID | None
    calendar_layout: Literal["day", "week", "month"] | None


@dataclass(frozen=True, kw_only=True)
class DatabaseSnapshot:
    id: UUID
    name: str
    color: str | None
    trashed: bool
    properties: tuple[PropertySnapshot, ...]
    records: tuple[RecordSnapshot, ...]
    views: tuple[ViewSnapshot, ...]


@dataclass(frozen=True, kw_only=True)
class WorkspaceArchive:
    format: Literal["ukladen.pages-databases"]
    version: Literal[1]
    pages: tuple[PageSnapshot, ...]
    databases: tuple[DatabaseSnapshot, ...]


class InvalidTransfer(ValueError):
    """A public, content-free explanation of a refused transfer."""
