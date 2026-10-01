from typing import Protocol
from uuid import UUID


class EmailAlreadyExists(Exception):
    """A user already owns the email address, compared case-insensitively."""


class UserRegistration(Protocol):
    """Create a user in the caller's transaction; raise EmailAlreadyExists on conflict."""

    def create(self, email: str) -> UUID: ...
