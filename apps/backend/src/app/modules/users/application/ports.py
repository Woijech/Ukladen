from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.users.domain.profile import UserProfile


class EmailAlreadyExists(Exception):
    """A user already owns the email address, compared case-insensitively."""


class UserRegistration(Protocol):
    """Create a user in the caller's transaction; raise EmailAlreadyExists on conflict."""

    def create(self, email: str) -> UUID: ...


class EmailVerifier(Protocol):
    """Read and update canonical email verification in the caller's transaction."""

    def get_unverified_email(self, user_id: UUID) -> str | None:
        """Lock an active, unverified user; return no email for an ineligible user."""
        ...

    def mark_verified(self, user_id: UUID, verified_at: datetime) -> bool: ...


class UserAuthentication(Protocol):
    """Look up and lock an active user by normalized email in the caller's transaction."""

    def get_active_id_by_email(self, email: str) -> UUID | None: ...

    def lock_active(self, user_id: UUID) -> bool:
        """Lock an active user by UUID until the caller's transaction completes."""
        ...

    def is_active(self, user_id: UUID) -> bool:
        """Read canonical user status without acquiring a row lock."""
        ...


class ProfileRepository(Protocol):
    """Read and update active canonical users in the caller's transaction."""

    def get_active(self, user_id: UUID) -> UserProfile | None: ...

    def update_active(self, user_id: UUID, changes: dict[str, str | None]) -> UserProfile | None:
        """Write only supplied columns; never commit independently."""
        ...

    def lock_active(self, user_id: UUID) -> UserProfile | None:
        """Read and lock an active user until transaction completion."""
        ...

    def update_avatar(self, user_id: UUID, key: str | None) -> UserProfile | None: ...

    def lock_avatar_key(self, user_id: UUID) -> str | None:
        """Read the canonical key under a lock, including disabled users, for compensation."""
        ...


class AvatarStorageUnavailable(Exception):
    """An avatar storage operation could not finish safely."""


class AvatarStorage(Protocol):
    def put(self, key: str, content: bytes) -> None: ...

    def get(self, key: str) -> bytes | None: ...

    def delete(self, key: str) -> None: ...


class AvatarImageProcessor(Protocol):
    def normalize(self, content: bytes, content_type: str) -> bytes:
        """Validate and return a metadata-free, square PNG, or raise InvalidAvatar."""
        ...
