import re
from collections.abc import Callable
from datetime import UTC, datetime
from hmac import compare_digest
from ipaddress import IPv4Address, IPv6Address
from uuid import UUID

from app.modules.auth.application.dto import IssuedSession, OAuthLinkContext, VerifiedGoogleIdentity
from app.modules.auth.application.ports import (
    CredentialRepository,
    GoogleIdentityRepository,
    PasswordHasher,
)
from app.modules.auth.application.registration import normalize_email
from app.modules.auth.application.service import SessionService
from app.modules.auth.domain.entities import AuthSession
from app.modules.auth.domain.errors import (
    InvalidCredentials,
    InvalidExternalIdentity,
    InvalidRegistration,
    InvalidSession,
)
from app.modules.users.application.ports import UserAuthentication


class GoogleLinkService:
    """Re-authenticate before initiation; complete under user/credential/session locks.

    Adapters share one caller-owned transaction. Roll back on failure and commit
    before issuing cookies. Only browser-bound, provider-verified callbacks may complete.
    """

    def __init__(
        self,
        users: UserAuthentication,
        credentials: CredentialRepository,
        passwords: PasswordHasher,
        identities: GoogleIdentityRepository,
        sessions: SessionService,
        *,
        hash_token: Callable[[str], str],
        dummy_password_hash: str,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.users = users
        self.credentials = credentials
        self.passwords = passwords
        self.identities = identities
        self.sessions = sessions
        self.hash_token = hash_token
        self.dummy_password_hash = dummy_password_hash
        self.now = now

    def _require_session(self, user_id: UUID, session_id: UUID, token_hash: str) -> None:
        stored = self.sessions.repository.get_for_user(session_id, user_id)
        if stored is None or not compare_digest(stored.token_hash, token_hash):
            raise InvalidSession("Invalid or expired session.")
        stored.require_active(self.now())

    def prepare(self, current: AuthSession, password: str) -> OAuthLinkContext:
        if not 1 <= len(password) <= 1024 or not self.users.lock_active(current.user_id):
            raise InvalidCredentials("Invalid current password.")
        stored_hash = self.credentials.get_password_hash(current.user_id)
        valid = self.passwords.verify(password, stored_hash or self.dummy_password_hash)
        if stored_hash is None or not valid:
            raise InvalidCredentials("Invalid current password.")
        self._require_session(current.user_id, current.id, current.token_hash)
        return OAuthLinkContext(current.user_id, current.id, self.hash_token(stored_hash))

    def complete(
        self,
        identity: VerifiedGoogleIdentity,
        context: OAuthLinkContext,
        session_token: str | None,
        *,
        user_agent: str | None = None,
        ip_address: IPv4Address | IPv6Address | None = None,
    ) -> IssuedSession:
        if session_token is None or re.fullmatch(r"[A-Za-z0-9_-]{43}", session_token) is None:
            raise InvalidSession("Invalid or expired session.")
        if not self.users.lock_active(context.user_id):
            raise InvalidSession("Invalid or expired session.")
        stored_hash = self.credentials.get_password_hash(context.user_id)
        if stored_hash is None or not compare_digest(
            self.hash_token(stored_hash), context.password_fingerprint
        ):
            raise InvalidCredentials("Invalid current password.")
        self._require_session(context.user_id, context.session_id, self.hash_token(session_token))
        owner = self.identities.get_user_id(identity.subject)
        if owner is not None and owner != context.user_id:
            raise InvalidExternalIdentity("Google identity could not be linked.")
        if owner is None:
            try:
                email = normalize_email(identity.email)
            except InvalidRegistration:
                raise InvalidExternalIdentity("Google identity could not be linked.") from None
            self.identities.create(context.user_id, identity.subject, email, self.now())
        return self.sessions.create(context.user_id, user_agent=user_agent, ip_address=ip_address)
