from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from email.errors import HeaderParseError
from email.headerregistry import Address
from ipaddress import IPv4Address, IPv6Address
from uuid import uuid4

from app.core.config import Settings
from app.modules.auth.application.dto import RegistrationResult
from app.modules.auth.application.ports import PasswordHasher, RegistrationRepository
from app.modules.auth.application.service import SessionService
from app.modules.auth.domain.entities import OneTimeToken, TokenType
from app.modules.auth.domain.errors import InvalidRegistration, RegistrationConflict
from app.modules.users.application.ports import EmailAlreadyExists, UserRegistration


def normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not normalized or len(normalized) > 320:
        raise InvalidRegistration("Invalid email address.")
    try:
        address = Address(addr_spec=normalized)
    except ValueError, HeaderParseError:
        raise InvalidRegistration("Invalid email address.") from None
    if not address.username or not address.domain or address.addr_spec != normalized:
        raise InvalidRegistration("Invalid email address.")
    return normalized


class RegistrationService:
    """Use adapters sharing one transaction; roll back failures and commit before delivery."""

    def __init__(
        self,
        users: UserRegistration,
        repository: RegistrationRepository,
        passwords: PasswordHasher,
        sessions: SessionService,
        settings: Settings,
        *,
        generate_token: Callable[[], str],
        hash_token: Callable[[str], str],
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.users = users
        self.repository = repository
        self.passwords = passwords
        self.sessions = sessions
        self.minimum_password_length = settings.auth_password_min_length
        self.verification_lifetime = timedelta(seconds=settings.auth_email_verification_ttl_seconds)
        self.generate_token = generate_token
        self.hash_token = hash_token
        self.now = now

    def register(
        self,
        email: str,
        password: str,
        *,
        user_agent: str | None = None,
        ip_address: IPv4Address | IPv6Address | None = None,
    ) -> RegistrationResult:
        email = normalize_email(email)
        if not self.minimum_password_length <= len(password) <= 1024:
            raise InvalidRegistration(
                f"Password must contain between {self.minimum_password_length} and 1024 characters."
            )
        password_hash = self.passwords.hash(password)
        try:
            user_id = self.users.create(email)
        except EmailAlreadyExists:
            raise RegistrationConflict("Email is already registered.") from None
        now = self.now()
        self.repository.create_credential(user_id, password_hash, now)
        session = self.sessions.create(user_id, user_agent=user_agent, ip_address=ip_address)
        verification_token = self.generate_token()
        self.repository.create_one_time_token(
            OneTimeToken(
                id=uuid4(),
                user_id=user_id,
                token_type=TokenType.EMAIL_VERIFICATION,
                token_hash=self.hash_token(verification_token),
                created_at=now,
                expires_at=now + self.verification_lifetime,
            )
        )
        return RegistrationResult(user_id, email, session, verification_token)
