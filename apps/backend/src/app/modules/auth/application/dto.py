from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.modules.auth.domain.entities import AuthSession


@dataclass(frozen=True)
class IssuedSession:
    session: AuthSession
    token: str = field(repr=False)


@dataclass(frozen=True)
class RegistrationResult:
    user_id: UUID
    email: str
    session: IssuedSession
    verification_token: str = field(repr=False)


@dataclass(frozen=True)
class PasswordResetDelivery:
    """Internal delivery data; commit before sending, never return it from HTTP."""

    user_id: UUID
    email: str
    expires_at: datetime
    token: str = field(repr=False)
