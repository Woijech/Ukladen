import re
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from app.modules.auth.application.ports import EmailVerificationRepository
from app.modules.auth.domain.errors import InvalidOneTimeToken
from app.modules.users.application.ports import EmailVerifier


class EmailVerificationService:
    """Share one transaction between adapters; roll back failures and commit on success."""

    def __init__(
        self,
        repository: EmailVerificationRepository,
        users: EmailVerifier,
        *,
        hash_token: Callable[[str], str],
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.repository = repository
        self.users = users
        self.hash_token = hash_token
        self.now = now

    def confirm(self, token: str) -> UUID:
        if re.fullmatch(r"[A-Za-z0-9_-]{43}", token) is None:
            raise InvalidOneTimeToken("Invalid or expired token.")
        stored = self.repository.get_by_token_hash(self.hash_token(token))
        if stored is None:
            raise InvalidOneTimeToken("Invalid or expired token.")
        now = self.now()
        stored.consume(now)
        self.repository.mark_used(stored.id, now)
        if not self.users.mark_verified(stored.user_id, now):
            raise InvalidOneTimeToken("Invalid or expired token.")
        return stored.user_id
