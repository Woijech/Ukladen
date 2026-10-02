from datetime import datetime
from typing import Protocol
from uuid import UUID


class EmailAlreadyExists(Exception):
    """A user already owns the email address, compared case-insensitively."""


class UserRegistration(Protocol):
    """Create a user in the caller's transaction; raise EmailAlreadyExists on conflict."""

    def create(self, email: str) -> UUID: ...


class EmailVerifier(Protocol):
    """Record verification in the caller's transaction; return False for a missing user."""

    def mark_verified(self, user_id: UUID, verified_at: datetime) -> bool: ...


class UserAuthentication(Protocol):
    """Look up and lock an active user by normalized email in the caller's transaction."""

    def get_active_id_by_email(self, email: str) -> UUID | None: ...
