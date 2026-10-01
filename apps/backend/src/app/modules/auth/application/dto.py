from dataclasses import dataclass, field

from app.modules.auth.domain.entities import AuthSession


@dataclass(frozen=True)
class IssuedSession:
    session: AuthSession
    token: str = field(repr=False)
