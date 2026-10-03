from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.core.config import Settings
from app.modules.auth.application.dto import EmailVerificationDelivery
from app.modules.auth.application.ports import RegistrationRepository
from app.modules.auth.domain.entities import OneTimeToken, TokenType
from app.modules.users.application.ports import EmailVerifier


class EmailVerificationRequestService:
    """Share one transaction between adapters; commit before sending token data."""

    def __init__(
        self,
        users: EmailVerifier,
        repository: RegistrationRepository,
        settings: Settings,
        *,
        generate_token: Callable[[], str],
        hash_token: Callable[[str], str],
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.users = users
        self.repository = repository
        self.lifetime = timedelta(seconds=settings.auth_email_verification_ttl_seconds)
        self.generate_token = generate_token
        self.hash_token = hash_token
        self.now = now

    def request(self, user_id: UUID) -> EmailVerificationDelivery | None:
        email = self.users.get_unverified_email(user_id)
        if email is None:
            return None
        now = self.now()
        token = self.generate_token()
        expires_at = now + self.lifetime
        self.repository.create_one_time_token(
            OneTimeToken(
                id=uuid4(),
                user_id=user_id,
                token_type=TokenType.EMAIL_VERIFICATION,
                token_hash=self.hash_token(token),
                created_at=now,
                expires_at=expires_at,
            )
        )
        return EmailVerificationDelivery(user_id, email, expires_at, token)
