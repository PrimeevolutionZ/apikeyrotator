"""In-process state backend."""

from __future__ import annotations
import threading
import time
from collections.abc import Iterable

from .base import SharedState, StateBackend


class TokenBucket:
    """
    Classic token bucket: ``capacity`` tokens, refilled at ``refill_per_sec``.
    Not thread-safe by itself - InMemoryStateBackend guards it with a lock.
    """

    __slots__ = ("capacity", "refill_per_sec", "tokens", "updated")

    def __init__(self, capacity: int, refill_per_sec: float, now: float | None = None):
        self.capacity = float(capacity)
        self.refill_per_sec = float(refill_per_sec)
        self.tokens = float(capacity)
        self.updated = time.time() if now is None else now

    def acquire(self, now: float | None = None) -> float:
        """Takes a token; returns 0.0 on success or seconds until a token is available."""
        if now is None:
            now = time.time()
        elapsed = now - self.updated
        if elapsed > 0:
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_sec)
        self.updated = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return 0.0
        if self.refill_per_sec <= 0:
            return float("inf")
        return (1.0 - self.tokens) / self.refill_per_sec


class InMemoryStateBackend(StateBackend):
    """
    State kept in this process. Pass one instance to several rotators to share
    rate limits / invalid keys / token buckets between them (``shared=True``).
    """

    blocking = False

    def __init__(self, shared: bool = True, salt: bytes | None = None, invalid_ttl: float | None = 86400.0):
        self.shared = shared
        self.salt = salt
        #: Seconds a rejected key stays banned for other rotators (None = until clear_invalid)
        self.invalid_ttl = invalid_ttl
        self._lock = threading.Lock()
        self._buckets: dict[str, TokenBucket] = {}
        self._rate_limited: dict[str, float] = {}
        self._invalid: dict[str, float] = {}   # key_id -> time it is forgotten

    def report_rate_limited(self, key_id: str, until: float) -> None:
        with self._lock:
            if until > self._rate_limited.get(key_id, 0.0):
                self._rate_limited[key_id] = until

    def report_invalid(self, key_id: str) -> None:
        ttl = self.invalid_ttl
        with self._lock:
            self._invalid[key_id] = float('inf') if ttl is None else time.time() + ttl

    def clear_invalid(self, key_id: str | None = None) -> None:
        with self._lock:
            if key_id is None:
                self._invalid.clear()
            else:
                self._invalid.pop(key_id, None)

    def snapshot(self) -> SharedState:
        now = time.time()
        with self._lock:
            # Drop expired entries so the dict stays bounded
            for entries in (self._rate_limited, self._invalid):
                expired = [k for k, until in entries.items() if until <= now]
                for k in expired:
                    del entries[k]
            return SharedState(dict(self._rate_limited), frozenset(self._invalid))

    def acquire_token(self, key_id: str, capacity: int, refill_per_sec: float) -> float:
        with self._lock:
            bucket = self._buckets.get(key_id)
            if bucket is None:
                bucket = self._buckets[key_id] = TokenBucket(capacity, refill_per_sec)
            return bucket.acquire()

    def forget(self, key_ids: Iterable[str]) -> None:
        """Drops buckets of keys that are no longer used."""
        with self._lock:
            for k in key_ids:
                self._buckets.pop(k, None)
