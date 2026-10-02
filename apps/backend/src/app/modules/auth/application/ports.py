from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.auth.domain.entities import AuthSession, OneTimeToken


class SessionCacheUnavailable(Exception):
    """A cache operation could not finish safely."""


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password: str, password_hash: str) -> bool: ...


class RegistrationRepository(Protocol):
    """Persist credentials and one-time tokens in the caller's transaction."""

    def create_credential(
        self, user_id: UUID, password_hash: str, created_at: datetime
    ) -> None: ...

    def create_one_time_token(self, token: OneTimeToken) -> None: ...


class EmailVerificationRepository(Protocol):
    """Lock a verification token until transaction completion; mark it used under that lock."""

    def get_by_token_hash(self, token_hash: str) -> OneTimeToken | None: ...

    def mark_used(self, token_id: UUID, used_at: datetime) -> None: ...


class SessionRepository(Protocol):
    """Lookup locks rows until the caller completes its transaction."""

    def create(self, session: AuthSession) -> None: ...

    def get_by_token_hash(self, token_hash: str) -> AuthSession | None: ...

    def revoke(self, session_id: UUID) -> str | None: ...

    def revoke_all_for_user(self, user_id: UUID) -> list[str]: ...


class SessionCache(Protocol):
    """Cache operations raise SessionCacheUnavailable when they cannot finish."""

    def get(self, token_hash: str) -> AuthSession | None: ...

    def set(self, session: AuthSession) -> None: ...

    def delete(self, *token_hashes: str) -> None: ...
