from collections.abc import Callable
from datetime import UTC, datetime

from pydantic import TypeAdapter, ValidationError
from redis import Redis
from redis.exceptions import RedisError

from app.modules.auth.application.ports import SessionCacheUnavailable
from app.modules.auth.domain.entities import AuthSession
from app.modules.auth.domain.errors import InvalidSession


def _key(token_hash: str) -> str:
    return f"ukladen:auth:session:{token_hash}"


class RedisSessionCache:
    adapter = TypeAdapter(AuthSession)

    def __init__(
        self,
        redis: Redis,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.redis = redis
        self.now = now

    def get(self, token_hash: str) -> AuthSession | None:
        try:
            value = self.redis.get(_key(token_hash))
        except RedisError:
            raise SessionCacheUnavailable("Session cache is unavailable.") from None
        if not isinstance(value, str | bytes):
            return None
        try:
            session = self.adapter.validate_json(value)
            if session.token_hash != token_hash:
                return None
            session.require_active(self.now())
        except ValidationError, InvalidSession:
            return None
        return session

    def set(self, session: AuthSession) -> None:
        try:
            session.require_active(self.now())
        except InvalidSession:
            self.delete(session.token_hash)
            return
        try:
            self.redis.set(
                _key(session.token_hash),
                self.adapter.dump_json(session),
                pxat=int(session.expires_at.timestamp() * 1000),
            )
        except RedisError:
            raise SessionCacheUnavailable("Session cache is unavailable.") from None

    def delete(self, *token_hashes: str) -> None:
        if not token_hashes:
            return
        try:
            self.redis.delete(*(_key(token_hash) for token_hash in token_hashes))
        except RedisError:
            raise SessionCacheUnavailable("Session cache is unavailable.") from None
