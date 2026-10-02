import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address, IPv6Address
from uuid import UUID, uuid4

from app.core.config import Settings
from app.modules.auth.application.dto import IssuedSession
from app.modules.auth.application.ports import (
    SessionCache,
    SessionCacheUnavailable,
    SessionRepository,
)
from app.modules.auth.domain.entities import AuthSession
from app.modules.auth.domain.errors import InvalidSession, SessionNotFound


class SessionService:
    """Callers own transactions and must roll back on exceptions.

    Complete validation transactions before starting mutations or delivering new tokens.
    """

    def __init__(
        self,
        repository: SessionRepository,
        cache: SessionCache,
        settings: Settings,
        *,
        generate_token: Callable[[], str],
        hash_token: Callable[[str], str],
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.repository = repository
        self.cache = cache
        self.lifetime = timedelta(seconds=settings.auth_session_ttl_seconds)
        self.generate_token = generate_token
        self.hash_token = hash_token
        self.now = now

    def create(
        self,
        user_id: UUID,
        *,
        user_agent: str | None = None,
        ip_address: IPv4Address | IPv6Address | None = None,
    ) -> IssuedSession:
        token = self.generate_token()
        now = self.now()
        session = AuthSession(
            id=uuid4(),
            user_id=user_id,
            token_hash=self.hash_token(token),
            created_at=now,
            last_seen_at=now,
            expires_at=now + self.lifetime,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        self.repository.create(session)
        # Publish only through validation after the caller commits and delivers the cookie.
        return IssuedSession(session=session, token=token)

    def validate(self, token: str) -> AuthSession:
        if re.fullmatch(r"[A-Za-z0-9_-]{43}", token) is None:
            raise InvalidSession("Invalid or expired session.")
        token_hash = self.hash_token(token)
        try:
            cached = self.cache.get(token_hash)
            if cached is not None and cached.token_hash == token_hash:
                cached.require_active(self.now())
                return cached
        except SessionCacheUnavailable, InvalidSession:
            pass
        session = self.repository.get_by_token_hash(token_hash)
        if session is None:
            raise InvalidSession("Invalid or expired session.")
        session.require_active(self.now())
        try:
            self.cache.set(session)
        except SessionCacheUnavailable:
            pass
        return session

    def revoke(self, session_id: UUID) -> None:
        token_hash = self.repository.revoke(session_id)
        if token_hash is not None:
            self.cache.delete(token_hash)

    def list_active_for_user(self, user_id: UUID) -> list[AuthSession]:
        return self.repository.list_active_for_user(user_id, self.now())

    def revoke_for_user(self, session_id: UUID, user_id: UUID) -> None:
        token_hash = self.repository.revoke_for_user(session_id, user_id)
        if token_hash is None:
            raise SessionNotFound("Session not found.")
        self.cache.delete(token_hash)

    def revoke_all_for_user(self, user_id: UUID) -> None:
        self.cache.delete(*self.repository.revoke_all_for_user(user_id))
