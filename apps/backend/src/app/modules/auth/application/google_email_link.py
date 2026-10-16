import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hmac import compare_digest
from ipaddress import IPv4Address, IPv6Address
from uuid import UUID, uuid4

from app.core.config import Settings
from app.modules.auth.application.dto import (
    GoogleEmailDelivery,
    IssuedSession,
    OAuthLinkContext,
    VerifiedGoogleIdentity,
)
from app.modules.auth.application.google_link import GoogleLinkService
from app.modules.auth.application.ports import (
    CredentialRepository,
    GoogleEmailConfirmationRepository,
    GoogleIdentityRepository,
)
from app.modules.auth.application.registration import normalize_email
from app.modules.auth.application.service import SessionService
from app.modules.auth.domain.entities import GoogleEmailConfirmation, OneTimeToken, TokenType
from app.modules.auth.domain.errors import InvalidExternalIdentity, InvalidOneTimeToken
from app.modules.users.application.ports import ProfileRepository


class GoogleEmailLinkService:
    def __init__(
        self,
        users: ProfileRepository,
        credentials: CredentialRepository,
        identities: GoogleIdentityRepository,
        repository: GoogleEmailConfirmationRepository,
        links: GoogleLinkService,
        sessions: SessionService,
        settings: Settings,
        *,
        generate_token: Callable[[], str],
        hash_token: Callable[[str], str],
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.users, self.credentials, self.identities = users, credentials, identities
        self.repository, self.links, self.sessions = repository, links, sessions
        self.generate_token, self.hash_token, self.now = generate_token, hash_token, now
        self.lifetime = timedelta(seconds=settings.auth_oauth_state_ttl_seconds)

    def prepare(
        self,
        user_id: UUID,
        identity: VerifiedGoogleIdentity,
        browser_token: str | None,
        context: OAuthLinkContext | None = None,
        session_token: str | None = None,
    ) -> GoogleEmailDelivery:
        if browser_token is None or re.fullmatch(r"[A-Za-z0-9_-]{43}", browser_token) is None:
            raise InvalidExternalIdentity("Google identity could not be linked.")
        user = self.users.lock_active(user_id)
        password_hash = self.credentials.get_password_hash(user_id)
        if user is None or user.email_verified_at is None or password_hash is None:
            raise InvalidExternalIdentity("Google identity could not be linked.")
        if context is not None:
            self.links.validate(context, session_token)
        elif normalize_email(user.email) != normalize_email(identity.email):
            raise InvalidExternalIdentity("Google identity could not be linked.")
        token, now = self.generate_token(), self.now()
        self.repository.create(
            GoogleEmailConfirmation(
                token=OneTimeToken(
                    id=uuid4(),
                    user_id=user_id,
                    token_type=TokenType.EMAIL_VERIFICATION,
                    token_hash=self.hash_token(token),
                    created_at=now,
                    expires_at=now + self.lifetime,
                ),
                subject=identity.subject,
                email=identity.email,
                canonical_email=user.email,
                browser_token_hash=self.hash_token(browser_token),
                password_fingerprint=self.hash_token(password_hash),
                session_id=context.session_id if context is not None else None,
            )
        )
        return GoogleEmailDelivery(identity.email, token)

    def confirm(
        self,
        token: str,
        browser_token: str | None,
        session_token: str | None,
        *,
        user_agent: str | None = None,
        ip_address: IPv4Address | IPv6Address | None = None,
    ) -> IssuedSession:
        if (
            re.fullmatch(r"[A-Za-z0-9_-]{43}", token) is None
            or browser_token is None
            or re.fullmatch(r"[A-Za-z0-9_-]{43}", browser_token) is None
        ):
            raise InvalidOneTimeToken("Invalid or expired token.")
        record = self.repository.get_by_token_hash(self.hash_token(token))
        if record is None or not compare_digest(
            record.browser_token_hash, self.hash_token(browser_token)
        ):
            raise InvalidOneTimeToken("Invalid or expired token.")
        user = self.users.lock_active(record.token.user_id)
        password_hash = self.credentials.get_password_hash(record.token.user_id)
        if (
            user is None
            or user.email_verified_at is None
            or user.email != record.canonical_email
            or password_hash is None
            or not compare_digest(record.password_fingerprint, self.hash_token(password_hash))
        ):
            raise InvalidOneTimeToken("Invalid or expired token.")
        now = self.now()
        record.token.consume(now)
        self.repository.mark_used(record.token.id, now)
        identity = VerifiedGoogleIdentity(record.subject, record.email)
        if record.session_id is not None:
            return self.links.complete(
                identity,
                OAuthLinkContext(user.id, record.session_id, record.password_fingerprint),
                session_token,
                user_agent=user_agent,
                ip_address=ip_address,
            )
        owner = self.identities.get_user_id(identity.subject)
        if owner is not None and owner != user.id:
            raise InvalidExternalIdentity("Google identity could not be linked.")
        if owner is None:
            self.identities.create(user.id, identity.subject, identity.email, now)
        return self.sessions.create(user.id, user_agent=user_agent, ip_address=ip_address)
