from collections.abc import Callable
from datetime import UTC, datetime
from ipaddress import IPv4Address, IPv6Address
from uuid import UUID

from app.modules.auth.application.dto import IssuedSession, VerifiedGoogleIdentity
from app.modules.auth.application.ports import CredentialRepository, GoogleIdentityRepository
from app.modules.auth.application.registration import normalize_email
from app.modules.auth.application.service import SessionService
from app.modules.auth.domain.errors import (
    AccountLinkingRequired,
    InvalidExternalIdentity,
    InvalidRegistration,
)
from app.modules.users.application.ports import (
    EmailAlreadyExists,
    EmailVerifier,
    ProfileRepository,
    UserAuthentication,
    UserRegistration,
)


class GoogleLoginService:
    """Accept only verified identities after browser-state validation.

    Share one transaction across adapters, roll back on any exception, and commit
    before delivering the issued session. No provider tokens enter this service.
    """

    def __init__(
        self,
        users: UserRegistration,
        authentication: UserAuthentication,
        verifier: EmailVerifier,
        identities: GoogleIdentityRepository,
        sessions: SessionService,
        *,
        profiles: ProfileRepository,
        credentials: CredentialRepository,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.users = users
        self.authentication = authentication
        self.verifier = verifier
        self.identities = identities
        self.sessions = sessions
        self.profiles = profiles
        self.credentials = credentials
        self.now = now

    def login(
        self,
        identity: VerifiedGoogleIdentity,
        *,
        user_agent: str | None = None,
        ip_address: IPv4Address | IPv6Address | None = None,
    ) -> IssuedSession:
        user_id = self.identities.get_user_id(identity.subject)
        if user_id is not None and identity.email_authoritative:
            profile = self.profiles.lock_active(user_id)
            if (
                profile is not None
                and profile.email_verified_at is None
                and normalize_email(profile.email) == normalize_email(identity.email)
                and self.credentials.get_password_hash(user_id) is None
            ):
                if not self.verifier.mark_verified(user_id, self.now()):
                    raise InvalidExternalIdentity("Google identity could not be resolved.")
        if user_id is None:
            try:
                email = normalize_email(identity.email)
            except InvalidRegistration:
                raise InvalidExternalIdentity("Google identity could not be resolved.") from None
            try:
                user_id = self.users.create(email)
            except EmailAlreadyExists:
                # A concurrent first login may have committed this subject while we waited.
                user_id = self.identities.get_user_id(identity.subject)
                if user_id is None:
                    candidate = self.authentication.get_active_id_by_email(email)
                    profile = self.profiles.get_active(candidate) if candidate is not None else None
                    owner = (
                        self.identities.get_user_id(identity.subject)
                        if profile is not None
                        else None
                    )
                    if profile is not None and owner == profile.id:
                        return self.sessions.create(
                            profile.id, user_agent=user_agent, ip_address=ip_address
                        )
                    if (
                        not identity.email_authoritative
                        or profile is None
                        or profile.email_verified_at is None
                        or self.identities.has_for_user(profile.id)
                    ):
                        raise AccountLinkingRequired("Account linking is required.") from None
                    user_id = profile.id
                    self.identities.create(user_id, identity.subject, email, self.now())
            else:
                now = self.now()
                if identity.email_authoritative and not self.verifier.mark_verified(user_id, now):
                    raise InvalidExternalIdentity("Google identity could not be resolved.")
                self.identities.create(user_id, identity.subject, email, now)
        if not self.authentication.lock_active(user_id):
            raise InvalidExternalIdentity("Google identity could not be resolved.")
        return self.sessions.create(user_id, user_agent=user_agent, ip_address=ip_address)

    def email_link_target(self, identity: VerifiedGoogleIdentity) -> UUID:
        user_id = self.authentication.get_active_id_by_email(normalize_email(identity.email))
        profile = self.profiles.get_active(user_id) if user_id is not None else None
        if (
            identity.email_authoritative
            or profile is None
            or profile.email_verified_at is None
            or self.identities.has_for_user(profile.id)
        ):
            raise AccountLinkingRequired("Account linking is required.")
        return profile.id
