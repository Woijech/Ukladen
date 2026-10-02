import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.core.config import Settings
from app.modules.auth.application.dto import PasswordResetDelivery
from app.modules.auth.application.ports import (
    CredentialRepository,
    PasswordHasher,
    PasswordResetRepository,
)
from app.modules.auth.application.registration import normalize_email
from app.modules.auth.application.service import SessionService
from app.modules.auth.domain.entities import OneTimeToken, TokenType
from app.modules.auth.domain.errors import InvalidOneTimeToken, InvalidPassword, InvalidRegistration
from app.modules.users.application.ports import UserAuthentication


class PasswordRecoveryService:
    """Share one transaction between adapters; roll back errors and commit before delivery."""

    def __init__(
        self,
        users: UserAuthentication,
        credentials: CredentialRepository,
        repository: PasswordResetRepository,
        passwords: PasswordHasher,
        sessions: SessionService,
        settings: Settings,
        *,
        generate_token: Callable[[], str],
        hash_token: Callable[[str], str],
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.users = users
        self.credentials = credentials
        self.repository = repository
        self.passwords = passwords
        self.sessions = sessions
        self.minimum_password_length = settings.auth_password_min_length
        self.lifetime = timedelta(seconds=settings.auth_password_reset_ttl_seconds)
        self.generate_token = generate_token
        self.hash_token = hash_token
        self.now = now

    def request_reset(self, email: str) -> PasswordResetDelivery | None:
        try:
            email = normalize_email(email)
        except InvalidRegistration:
            return None
        user_id = self.users.get_active_id_by_email(email)
        if user_id is None or self.credentials.get_password_hash(user_id) is None:
            return None
        token = self.generate_token()
        now = self.now()
        stored = OneTimeToken(
            id=uuid4(),
            user_id=user_id,
            token_type=TokenType.PASSWORD_RESET,
            token_hash=self.hash_token(token),
            created_at=now,
            expires_at=now + self.lifetime,
        )
        self.repository.create(stored)
        return PasswordResetDelivery(user_id, email, stored.expires_at, token)

    def confirm_reset(self, token: str, new_password: str) -> UUID:
        if re.fullmatch(r"[A-Za-z0-9_-]{43}", token) is None:
            raise InvalidOneTimeToken("Invalid or expired token.")
        if not self.minimum_password_length <= len(new_password) <= 1024:
            raise InvalidPassword(
                f"Password must contain between {self.minimum_password_length} and 1024 characters."
            )
        # Hash before acquiring database locks; check expiry only after acquiring them.
        password_hash = self.passwords.hash(new_password)
        stored = self.repository.get_by_token_hash(self.hash_token(token))
        if stored is None or stored.token_type != TokenType.PASSWORD_RESET:
            raise InvalidOneTimeToken("Invalid or expired token.")
        if (
            not self.users.lock_active(stored.user_id)
            or self.credentials.get_password_hash(stored.user_id) is None
        ):
            raise InvalidOneTimeToken("Invalid or expired token.")
        now = self.now()
        stored.consume(now)
        if not self.credentials.update_password_hash(stored.user_id, password_hash, now):
            raise InvalidOneTimeToken("Invalid or expired token.")
        self.repository.mark_used(stored.id, now)
        self.sessions.revoke_all_for_user(stored.user_id)
        return stored.user_id
