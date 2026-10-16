from datetime import UTC, datetime
from hmac import compare_digest

from app.core.config import Settings
from app.modules.auth.application.dto import RegistrationState
from app.modules.auth.application.ports import (
    CredentialRepository,
    PasswordHasher,
    RegistrationRepository,
)
from app.modules.auth.application.service import SessionService
from app.modules.auth.domain.entities import AuthSession
from app.modules.auth.domain.errors import (
    InvalidPassword,
    InvalidSession,
    RegistrationConflict,
    RegistrationIncomplete,
)
from app.modules.users.application.ports import ProfileRepository


class RegistrationAccessService:
    def __init__(
        self,
        users: ProfileRepository,
        credentials: CredentialRepository,
        registration: RegistrationRepository,
        passwords: PasswordHasher,
        sessions: SessionService,
        settings: Settings,
    ) -> None:
        self.users = users
        self.credentials = credentials
        self.registration = registration
        self.passwords = passwords
        self.sessions = sessions
        self.minimum_password_length = settings.auth_password_min_length

    def state(self, current: AuthSession) -> RegistrationState:
        user = self.users.get_active(current.user_id)
        if user is None:
            raise InvalidSession("Invalid or expired session.")
        return RegistrationState(
            user.email,
            user.email_verified_at is not None,
            self.credentials.get_password_hash(user.id) is None,
        )

    def require_complete(self, current: AuthSession) -> None:
        if not self.state(current).complete:
            raise RegistrationIncomplete("Registration is incomplete.")

    def set_password(self, current: AuthSession, password: str) -> None:
        if not self.minimum_password_length <= len(password) <= 1024:
            raise InvalidPassword("Invalid password.")
        password_hash = self.passwords.hash(password)
        if self.users.lock_active(current.user_id) is None:
            raise InvalidSession("Invalid or expired session.")
        if self.credentials.get_password_hash(current.user_id) is not None:
            raise RegistrationConflict("A password is already configured.")
        stored = self.sessions.repository.get_for_user(current.id, current.user_id)
        if stored is None or not compare_digest(stored.token_hash, current.token_hash):
            raise InvalidSession("Invalid or expired session.")
        now = datetime.now(UTC)
        stored.require_active(now)
        self.registration.create_credential(current.user_id, password_hash, now)
        self.sessions.revoke_others_for_user(current.user_id, current.id)
