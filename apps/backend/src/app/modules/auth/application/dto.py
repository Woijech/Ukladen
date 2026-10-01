from dataclasses import dataclass, field
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
