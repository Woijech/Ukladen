import logging
from hmac import compare_digest

from pydantic import TypeAdapter, ValidationError
from redis import Redis
from redis.exceptions import RedisError

from app.core.logging import log_failure
from app.modules.auth.application.dto import OAuthStateRecord
from app.modules.auth.application.ports import OAuthStateUnavailable
from app.modules.auth.domain.errors import InvalidOAuthState

_CONSUME = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""


logger = logging.getLogger(__name__)


class RedisOAuthStateStore:
    adapter = TypeAdapter(OAuthStateRecord)

    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    def create(self, state_hash: str, record: OAuthStateRecord, ttl_seconds: int) -> None:
        try:
            created = self.redis.set(
                f"ukladen:auth:oauth:{state_hash}",
                self.adapter.dump_json(record),
                ex=ttl_seconds,
                nx=True,
            )
        except RedisError as error:
            log_failure(
                logger, "auth.oauth_state_failed", error, dependency="redis", operation="create"
            )
            raise OAuthStateUnavailable("OAuth state is unavailable.") from None
        if created is not True:
            logger.error("auth.oauth_state_collision")
            raise OAuthStateUnavailable("OAuth state is unavailable.")

    def consume(self, state_hash: str, browser_token_hash: str) -> OAuthStateRecord | None:
        key = f"ukladen:auth:oauth:{state_hash}"
        try:
            value = self.redis.get(key)
            if value is None:
                return None
            if not isinstance(value, str | bytes) or len(value) > 1024:
                raise InvalidOAuthState("Invalid or expired OAuth state.")
            try:
                payload = value.decode("utf-8") if isinstance(value, bytes) else value
                record = self.adapter.validate_json(payload, strict=True)
            except UnicodeDecodeError, ValidationError:
                raise InvalidOAuthState("Invalid or expired OAuth state.") from None
            if not compare_digest(record.browser_token_hash, browser_token_hash):
                return None
            consumed = self.redis.eval(_CONSUME, 1, key, payload)
        except RedisError as error:
            log_failure(
                logger, "auth.oauth_state_failed", error, dependency="redis", operation="consume"
            )
            raise OAuthStateUnavailable("OAuth state is unavailable.") from None
        if consumed == 0:
            return None
        if consumed != 1:
            logger.error("auth.oauth_state_invalid_result")
            raise OAuthStateUnavailable("OAuth state is unavailable.")
        return record
