from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from ipaddress import IPv4Address, IPv6Address
from uuid import UUID

from app.modules.auth.domain.errors import InvalidOneTimeToken, InvalidSession


def _require_aware(*timestamps: datetime | None) -> None:
    if any(timestamp is not None and timestamp.utcoffset() is None for timestamp in timestamps):
        raise ValueError("Authentication timestamps must be timezone-aware.")


class TokenType(StrEnum):
    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"


@dataclass(frozen=True, kw_only=True)
class AuthSession:
    id: UUID
    user_id: UUID
    token_hash: str = field(repr=False)
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    user_agent: str | None = None
    ip_address: IPv4Address | IPv6Address | None = None

    def __post_init__(self) -> None:
        _require_aware(self.created_at, self.last_seen_at, self.expires_at, self.revoked_at)

    def require_active(self, now: datetime) -> None:
        _require_aware(now)
        if self.revoked_at is not None or not self.created_at <= now < self.expires_at:
            raise InvalidSession("Invalid or expired session.")


@dataclass(kw_only=True)
class OneTimeToken:
    id: UUID
    user_id: UUID
    token_type: TokenType
    token_hash: str = field(repr=False)
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_aware(self.created_at, self.expires_at, self.used_at)

    def require_usable(self, now: datetime) -> None:
        _require_aware(now)
        if self.used_at is not None or not self.created_at <= now < self.expires_at:
            raise InvalidOneTimeToken("Invalid or expired token.")

    def consume(self, now: datetime) -> None:
        self.require_usable(now)
        self.used_at = now
