from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.workspace.domain.properties import PropertySpec, PropertyValue


@dataclass(frozen=True, kw_only=True)
class UserDatabase:
    id: UUID
    user_id: UUID
    name: str
    color: str | None
    version: int
    schema_version: int
    created_at: datetime
    updated_at: datetime
    trashed_at: datetime | None = None


@dataclass(frozen=True, kw_only=True)
class DatabaseProperty(PropertySpec):
    id: UUID
    user_id: UUID
    database_id: UUID
    position: int
    version: int
    created_at: datetime
    updated_at: datetime
    trashed_at: datetime | None = None


@dataclass(frozen=True, kw_only=True)
class DatabaseRecord:
    id: UUID
    user_id: UUID
    database_id: UUID
    page_id: UUID
    values: dict[str, PropertyValue]
    version: int
    created_at: datetime
    updated_at: datetime
    trashed_at: datetime | None = None
