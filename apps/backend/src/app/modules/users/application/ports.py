from datetime import datetime
from typing import Protocol
from uuid import UUID


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
