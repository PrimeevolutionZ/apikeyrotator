"""Redis state backend - shares state between processes and machines."""

from __future__ import annotations
import time
from typing import Any

from .base import SharedState, StateBackend


# Token bucket in one atomic script. Uses Redis server time so all instances
# share one clock. Returns the wait time as a string (Lua numbers -> integers).
_TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])
local t = redis.call('TIME')
local now = tonumber(t[1]) + tonumber(t[2]) / 1000000
local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then
    tokens = capacity
    ts = now
end
local elapsed = now - ts
if elapsed > 0 then
    tokens = math.min(capacity, tokens + elapsed * rate)
end
local wait = 0
if tokens >= 1 then
    tokens = tokens - 1
elseif rate > 0 then
    wait = (1 - tokens) / rate
else
    wait = -1
end
redis.call('HSET', key, 'tokens', tostring(tokens), 'ts', tostring(now))
redis.call('EXPIRE', key, ttl)
return tostring(wait)
"""


def _decode(value: Any) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


class RedisStateBackend(StateBackend):
    """
    Shared state in Redis (``pip install apikeyrotator[redis]``).

    Stores, under ``{namespace}:*``:
    - ``rl``      sorted set: key_id -> UNIX time until the key is rate limited
    - ``invalid`` set of key_ids rejected with 401/403
    - ``tb:{id}`` token bucket hashes (atomic Lua script, Redis server clock)

    Only key hashes are stored (see :func:`key_id`), never raw API keys.

    Example:
        >>> backend = RedisStateBackend(url="redis://localhost:6379/0", namespace="openai")
        >>> rotator = APIKeyRotator(api_keys=[...], state_backend=backend, key_rate_limit=(60, 60))
    """

    shared = True
    blocking = True

    def __init__(
            self,
            client: Any = None,
            url: str | None = None,
            namespace: str = "apikeyrotator",
            salt: bytes | None = None,
            bucket_ttl: int = 3600,
    ):
        """
        Args:
            client: A ``redis.Redis`` client (sync). Created from ``url`` if omitted.
            url: Redis URL, default ``redis://localhost:6379/0``.
            namespace: Prefix for all Redis keys - use one per upstream provider.
            salt: Optional HMAC salt for key ids (same value on all instances).
            bucket_ttl: Seconds after which idle token buckets expire.
        """
        if client is None:
            try:
                import redis
            except ImportError as e:
                raise ImportError(
                    "RedisStateBackend requires redis: pip install 'apikeyrotator[redis]'"
                ) from e
            client = redis.Redis.from_url(url or "redis://localhost:6379/0")
        self._r = client
        self.namespace = namespace
        self.salt = salt
        self.bucket_ttl = int(bucket_ttl)
        self._rl = f"{namespace}:rl"
        self._invalid = f"{namespace}:invalid"
        self._bucket_script = client.register_script(_TOKEN_BUCKET_LUA)

    def report_rate_limited(self, key_id: str, until: float) -> None:
        # GT: only move the deadline forward (new members are always added)
        self._r.zadd(self._rl, {key_id: until}, gt=True)

    def report_invalid(self, key_id: str) -> None:
        self._r.sadd(self._invalid, key_id)

    def clear_invalid(self, key_id: str | None = None) -> None:
        if key_id is None:
            self._r.delete(self._invalid)
        else:
            self._r.srem(self._invalid, key_id)

    def snapshot(self) -> SharedState:
        now = time.time()
        pipe = self._r.pipeline(transaction=False)
        pipe.zremrangebyscore(self._rl, "-inf", now)
        pipe.zrangebyscore(self._rl, now, "+inf", withscores=True)
        pipe.smembers(self._invalid)
        _, limited, invalid = pipe.execute()
        return SharedState(
            {_decode(member): float(score) for member, score in limited},
            frozenset(_decode(member) for member in invalid),
        )

    def acquire_token(self, key_id: str, capacity: int, refill_per_sec: float) -> float:
        result = self._bucket_script(
            keys=[f"{self.namespace}:tb:{key_id}"],
            args=[capacity, refill_per_sec, self.bucket_ttl],
        )
        wait = float(_decode(result))
        return float("inf") if wait < 0 else wait

    def close(self) -> None:
        close = getattr(self._r, "close", None)
        if close is not None:
            close()
