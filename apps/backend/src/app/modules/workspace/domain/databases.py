from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


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
