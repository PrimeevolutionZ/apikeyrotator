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


# Every deadline is computed on the Redis server clock: clients only send durations,
# so clock skew between machines does not change how long a key stays parked.
_SERVER_NOW_LUA = """
local t = redis.call('TIME')
local now = tonumber(t[1]) + tonumber(t[2]) / 1000000
"""

# KEYS[1] = zset; ARGV[1] = member, ARGV[2] = seconds from now (< 0: forever)
_PARK_LUA = _SERVER_NOW_LUA + """
local seconds = tonumber(ARGV[2])
local score = '+inf'
if seconds >= 0 then
    score = tostring(now + seconds)
end
redis.call('ZADD', KEYS[1], 'GT', score, ARGV[1])
return 1
"""

# KEYS[1] = rate-limited zset, KEYS[2] = revoked zset; drops expired entries and returns
# {server now, [member, score, ...], [member, ...]}
_SNAPSHOT_LUA = _SERVER_NOW_LUA + """
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', now)
return {tostring(now), redis.call('ZRANGE', KEYS[1], 0, -1, 'WITHSCORES'), redis.call('ZRANGE', KEYS[2], 0, -1)}
"""


def _decode(value: Any) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


class RedisStateBackend(StateBackend):
    """
    Shared state in Redis (``pip install apikeyrotator[redis]``).

    Stores, under ``{namespace}:*`` (all times on the Redis server clock):
    - ``rl``      sorted set: key_id -> time until the key is rate limited
    - ``revoked`` sorted set: key_id rejected with 401/403 -> time it is forgotten
    - ``tb:{id}`` token bucket hashes (atomic Lua script)

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
            socket_timeout: float | None = 1.0,
            invalid_ttl: float | None = 86400.0,
    ):
        """
        Args:
            client: A ``redis.Redis`` client (sync). Created from ``url`` if omitted.
            url: Redis URL, default ``redis://localhost:6379/0``.
            namespace: Prefix for all Redis keys - use one per upstream provider.
            salt: Optional HMAC salt for key ids (same value on all instances).
            bucket_ttl: Seconds after which idle token buckets expire.
            socket_timeout: Connect / read timeout of the client created from ``url``
                (an unreachable Redis must not stall requests; ignored with ``client``).
            invalid_ttl: Seconds a key rejected with 401/403 stays banned for other
                instances (default one day; None = until ``clear_invalid``). A process
                that got the rejection itself does not use the key again until restarted.
        """
        if client is None:
            try:
                import redis
            except ImportError as e:
                raise ImportError(
                    "RedisStateBackend requires redis: pip install 'apikeyrotator[redis]'"
                ) from e
            client = redis.Redis.from_url(url or "redis://localhost:6379/0", socket_timeout=socket_timeout,
                                          socket_connect_timeout=socket_timeout)
        self._r = client
        self.namespace = namespace
        self.salt = salt
        self.bucket_ttl = int(bucket_ttl)
        self.invalid_ttl = invalid_ttl
        self._rl = f"{namespace}:rl"
        self._revoked = f"{namespace}:revoked"
        self._legacy_invalid = f"{namespace}:invalid"   # set without expiry, used before 0.9.2
        self._bucket_script = client.register_script(_TOKEN_BUCKET_LUA)
        self._park_script = client.register_script(_PARK_LUA)
        self._snapshot_script = client.register_script(_SNAPSHOT_LUA)

    def report_rate_limited(self, key_id: str, until: float) -> None:
        # Only the remaining duration is sent; GT only ever moves a deadline forward
        self._park_script(keys=[self._rl], args=[key_id, max(0.0, until - time.time())])

    def report_invalid(self, key_id: str) -> None:
        ttl = self.invalid_ttl
        self._park_script(keys=[self._revoked], args=[key_id, -1 if ttl is None else ttl])

    def clear_invalid(self, key_id: str | None = None) -> None:
        if key_id is None:
            self._r.delete(self._revoked, self._legacy_invalid)
        else:
            self._r.zrem(self._revoked, key_id)
            self._r.srem(self._legacy_invalid, key_id)

    def snapshot(self) -> SharedState:
        server_now, limited, revoked = self._snapshot_script(keys=[self._rl, self._revoked])
        # Server deadlines -> local clock: only the remaining time is taken from Redis
        offset = time.time() - float(_decode(server_now))
        pairs = iter(limited)
        return SharedState(
            {_decode(member): float(_decode(score)) + offset for member, score in zip(pairs, pairs)},
            frozenset(_decode(member) for member in revoked),
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
