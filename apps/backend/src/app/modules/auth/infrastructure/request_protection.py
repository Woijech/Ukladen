from redis import Redis
from redis.exceptions import RedisError

from app.modules.auth.application.ports import RateLimiterUnavailable

_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return {count, redis.call('TTL', KEYS[1])}
"""


class RedisRateLimiter:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    def check(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        try:
            result = self.redis.eval(_SCRIPT, 1, f"ukladen:auth:rate:{key}", str(window_seconds))
        except RedisError:
            raise RateLimiterUnavailable("Request protection is unavailable.") from None
        if not isinstance(result, list) or len(result) != 2:
            raise RateLimiterUnavailable("Request protection is unavailable.")
        count, ttl = result
        if not isinstance(count, int) or not isinstance(ttl, int):
            raise RateLimiterUnavailable("Request protection is unavailable.")
        if count < 1 or ttl < 0:
            raise RateLimiterUnavailable("Request protection is unavailable.")
        return count <= limit, max(1, ttl)
