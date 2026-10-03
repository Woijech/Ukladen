from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.auth.domain.entities import AuthSession, OneTimeToken


class SessionCacheUnavailable(Exception):
    """A cache operation could not finish safely."""


class RateLimiterUnavailable(Exception):
    """Request protection could not finish safely."""


class EmailDeliveryUnavailable(Exception):
    """An authentication email could not be queued or delivered safely."""


class EmailSender(Protocol):
    """Send or enqueue internal token data only after its database transaction commits."""

    def send_email_verification(self, email: str, token: str) -> None: ...

    def send_password_reset(self, email: str, token: str) -> None: ...


class RateLimiter(Protocol):
    def check(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        """Return whether the request is allowed and seconds until the window expires."""
        ...


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password: str, password_hash: str) -> bool: ...


class CredentialRepository(Protocol):
    """Look up and lock password credentials until the caller's transaction completes."""

    def get_password_hash(self, user_id: UUID) -> str | None: ...

    def update_password_hash(self, user_id: UUID, password_hash: str, updated_at: datetime) -> bool:
        """Update an existing credential in the caller's transaction; never create one."""
        ...


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


class PasswordResetRepository(Protocol):
    """Persist reset tokens; lookup holds a row lock until transaction completion."""

    def create(self, token: OneTimeToken) -> None: ...

    def get_by_token_hash(self, token_hash: str) -> OneTimeToken | None: ...

    def mark_used(self, token_id: UUID, used_at: datetime) -> None: ...


class SessionRepository(Protocol):
    """Token lookup locks rows until the caller completes its transaction."""

    def create(self, session: AuthSession) -> None: ...

    def get_by_token_hash(self, token_hash: str) -> AuthSession | None: ...

    def get_for_user(self, session_id: UUID, user_id: UUID) -> AuthSession | None:
        """Lock an owned session until transaction completion."""
        ...

    def list_active_for_user(self, user_id: UUID, now: datetime) -> list[AuthSession]: ...

    def revoke_for_user(self, session_id: UUID, user_id: UUID) -> str | None: ...

    def revoke(self, session_id: UUID) -> str | None: ...

    def revoke_all_for_user(self, user_id: UUID) -> list[str]: ...

    def revoke_others_for_user(self, user_id: UUID, current_session_id: UUID) -> list[str]: ...


class SessionCache(Protocol):
    """Cache operations raise SessionCacheUnavailable when they cannot finish."""

    def get(self, token_hash: str) -> AuthSession | None: ...

    def set(self, session: AuthSession) -> None: ...

    def delete(self, *token_hashes: str) -> None: ...
