from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.modules.ai.domain.state import InvalidAiState, require_time


class ConnectionUnavailable(Exception):
    pass


class ConnectionLimited(ConnectionUnavailable):
    def __init__(self, retry_after: int = 60) -> None:
        super().__init__("AI connection is temporarily limited.")
        self.retry_after = max(1, min(retry_after, 86400))


@dataclass(frozen=True, kw_only=True)
class PersonalConnection:
    id: UUID
    user_id: UUID
    label: str = field(repr=False)
    created_at: datetime
    encrypted_key: bytes | None = field(repr=False)
    encryption_key_id: str | None = field(repr=False)
    disconnected_at: datetime | None = None

    def __post_init__(self) -> None:
        require_time(self.created_at, self.disconnected_at)
        if self.label != self.label.strip() or not 1 <= len(self.label) <= 100:
            raise InvalidAiState("Invalid connection label.")
        active = self.disconnected_at is None
        if (
            (active and (self.encrypted_key is None or self.encryption_key_id is None))
            or (
                not active
                and (self.encrypted_key is not None or self.encryption_key_id is not None)
            )
            or (self.disconnected_at is not None and self.disconnected_at < self.created_at)
        ):
            raise InvalidAiState("Invalid connection lifecycle.")


@dataclass(frozen=True, kw_only=True)
class ModelSelection:
    offering_id: str | None = None
    offering_version: int | None = None
    connection_id: UUID | None = None
