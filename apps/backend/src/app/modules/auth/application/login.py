from ipaddress import IPv4Address, IPv6Address

from app.modules.auth.application.dto import IssuedSession
from app.modules.auth.application.ports import CredentialRepository, PasswordHasher
from app.modules.auth.application.registration import normalize_email
from app.modules.auth.application.service import SessionService
from app.modules.auth.domain.errors import InvalidCredentials, InvalidRegistration
from app.modules.users.application.ports import UserAuthentication


class LoginService:
    """Share one transaction across adapters; commit before delivering the session token.

    Build the dummy password hash once with the same hasher at application startup.
    """

    def __init__(
        self,
        users: UserAuthentication,
        credentials: CredentialRepository,
        passwords: PasswordHasher,
        sessions: SessionService,
        *,
        dummy_password_hash: str,
    ) -> None:
        self.users = users
        self.credentials = credentials
        self.passwords = passwords
        self.sessions = sessions
        self.dummy_password_hash = dummy_password_hash

    def login(
        self,
        email: str,
        password: str,
        *,
        user_agent: str | None = None,
        ip_address: IPv4Address | IPv6Address | None = None,
    ) -> IssuedSession:
        try:
            email = normalize_email(email)
        except InvalidRegistration:
            raise InvalidCredentials("Invalid email or password.") from None
        if not 1 <= len(password) <= 1024:
            raise InvalidCredentials("Invalid email or password.")
        user_id = self.users.get_active_id_by_email(email)
        password_hash = self.credentials.get_password_hash(user_id) if user_id is not None else None
        valid = self.passwords.verify(password, password_hash or self.dummy_password_hash)
        if user_id is None or not password_hash or not valid:
            raise InvalidCredentials("Invalid email or password.")
        return self.sessions.create(user_id, user_agent=user_agent, ip_address=ip_address)
