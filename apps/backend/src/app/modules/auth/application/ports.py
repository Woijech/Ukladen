from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.auth.application.dto import OAuthStateRecord, VerifiedGoogleIdentity
from app.modules.auth.domain.entities import AuthSession, OneTimeToken


class SessionCacheUnavailable(Exception):
    """A cache operation could not finish safely."""


class RateLimiterUnavailable(Exception):
    """Request protection could not finish safely."""


class EmailDeliveryUnavailable(Exception):
    """An authentication email could not be queued or delivered safely."""


class ExternalIdentityUnavailable(Exception):
    """Provider configuration or communication is unavailable."""


class OAuthStateUnavailable(Exception):
    """OAuth state could not be stored or consumed safely."""


class OAuthStateStore(Protocol):
    """Expiring state, separate from canonical users and sessions."""

    def create(self, state_hash: str, record: OAuthStateRecord, ttl_seconds: int) -> None:
        """Create without overwriting; raise OAuthStateUnavailable on failure."""
        ...

    def consume(self, state_hash: str, browser_token_hash: str) -> OAuthStateRecord | None:
        """Atomically consume once only for the matching browser; fail closed on outages."""
        ...


class ExternalIdentityProvider(Protocol):
    """Callers must validate and consume browser-bound OAuth state before resolving a callback."""

    def build_authorization_url(self, *, state: str, nonce: str, code_challenge: str) -> str: ...

    def resolve_callback(
        self, *, code: str, code_verifier: str, nonce: str
    ) -> VerifiedGoogleIdentity: ...


class GoogleIdentityRepository(Protocol):
    """Resolve Google subjects and insert identities in the caller's transaction."""

    def get_user_id(self, subject: str) -> UUID | None: ...

    def create(self, user_id: UUID, subject: str, email: str, created_at: datetime) -> None:
        """Never overwrite a subject's owner; conflicts raise InvalidExternalIdentity."""
        ...


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
