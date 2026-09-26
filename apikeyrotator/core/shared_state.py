"""Synchronisation of rate-limit / invalid-key state with a StateBackend (e.g. Redis)."""

from __future__ import annotations
import logging
import time
from collections.abc import Callable

from apikeyrotator.state import InMemoryStateBackend, SharedState, StateBackend

from .keys import KeyPool
from .util import mask_key


#: Deferred backend write: (method name, args). Collected during an attempt and
#: flushed by the request engine, so async rotators can run it off the event loop.
Report = tuple[str, tuple]

_HASHER = StateBackend()

#: After a backend error, calls are skipped for this many seconds (so an outage costs one
#: timeout per interval, not one per request); token buckets are kept locally meanwhile
BACKEND_RETRY_INTERVAL = 5.0


class StateSync:
    """
    Keeps the local key pool and a shared StateBackend in sync.

    Everything is best effort: a backend outage is logged (at most every 30s)
    and requests continue with local state ("fail open"). While the backend is
    down, ``key_rate_limit`` is enforced per process by local token buckets.
    """

    __slots__ = ('backend', 'shared', 'sync_interval', 'pool', 'logger', '_on_invalid',
                 '_last_sync', '_key_ids', 'invalid_ids', '_error_logged_at', '_down_until',
                 '_local_buckets', '_rejected_here')

    def __init__(self, backend: StateBackend | None, sync_interval: float, pool: KeyPool,
                 logger: logging.Logger, on_invalid: Callable[[str], object]):
        self.backend = backend
        self.shared = backend is not None and backend.shared
        self.sync_interval = max(0.0, sync_interval)
        self.pool = pool
        self.logger = logger
        self._on_invalid = on_invalid
        self._last_sync = float('-inf')
        self._key_ids: dict[str, str] = {}
        #: Ids of keys that must not be used: rejected here, or currently banned in the backend
        self.invalid_ids: set[str] = set()
        #: Rejected with 401/403 in this process - never used again here (no TTL)
        self._rejected_here: set[str] = set()
        # -inf, not 0.0: time.monotonic() counts from boot, so on a machine booted less
        # than 30 s ago (fresh CI runner, Lambda, new VM) the first error would be silent
        self._error_logged_at = float('-inf')
        self._down_until = float('-inf')
        self._local_buckets: InMemoryStateBackend | None = None

    @property
    def blocking(self) -> bool:
        """True if backend calls do network I/O (async rotators run them in a thread)."""
        backend = self.backend
        return backend is not None and backend.blocking

    # --- key ids (hashes - raw keys never leave the process) ---

    def key_id(self, key: str) -> str:
        kid = self._key_ids.get(key)
        if kid is None:
            backend = self.backend
            kid = (backend if backend is not None else _HASHER).key_id(key)
            self._key_ids[key] = kid
        return kid

    def forget_except(self, keys: list[str]) -> None:
        kept = set(keys)
        self._key_ids = {k: v for k, v in self._key_ids.items() if k in kept}

    def filter_invalid(self, keys: list[str]) -> list[str]:
        if not self.invalid_ids:
            return keys
        return [k for k in keys if self.key_id(k) not in self.invalid_ids]

    # --- pull ---

    def available(self) -> bool:
        """False for a while after a backend error."""
        return time.monotonic() >= self._down_until

    def sync_due(self) -> bool:
        if not self.shared:
            return False
        now = time.monotonic()
        if now < self._down_until:
            return False
        if now - self._last_sync < self.sync_interval:
            return False
        self._last_sync = now
        return True

    def apply(self, snapshot: SharedState) -> None:
        # Bans learned from other instances expire with the backend's invalid_ttl
        self.invalid_ids = self._rejected_here | snapshot.invalid
        if not snapshot.rate_limited and not snapshot.invalid:
            return
        by_id = {self.key_id(k): k for k in self.pool.keys()}
        for kid, until in snapshot.rate_limited.items():
            key = by_id.get(kid)
            if key is not None:
                self.pool.mark_rate_limited(key, until)
        for kid in snapshot.invalid:
            key = by_id.get(kid)
            if key is not None:
                self.logger.warning(f"Key {mask_key(key)} was invalidated by another instance")
                self._on_invalid(key)

    # --- push ---

    def report_rate_limited(self, reports: list[Report], key: str, until: float) -> None:
        if self.shared:
            reports.append(("report_rate_limited", (self.key_id(key), until)))

    def report_invalid(self, reports: list[Report], key: str) -> None:
        kid = self.key_id(key)
        self._rejected_here.add(kid)
        self.invalid_ids.add(kid)
        if self.shared:
            reports.append(("report_invalid", (kid,)))

    def flush(self, reports: list[Report]) -> None:
        backend = self.backend
        if backend is None or not reports or not self.available():
            return
        for method, args in reports:
            try:
                getattr(backend, method)(*args)
            except Exception as e:
                self.log_error(method, e)
                return

    # --- token buckets ---

    def acquire_token(self, key: str, capacity: int, refill_per_second: float) -> float:
        """Takes a token for `key`; returns seconds to wait (0 = acquired)."""
        kid = self.key_id(key)
        backend = self.backend
        if backend is not None and self.available():
            try:
                return backend.acquire_token(kid, capacity, refill_per_second)
            except Exception as e:
                self.log_error("acquire_token", e)
        # Backend down: limit this process on its own rather than not at all
        local = self._local_buckets
        if local is None:
            local = self._local_buckets = InMemoryStateBackend(shared=False)
        return local.acquire_token(kid, capacity, refill_per_second)

    def log_error(self, action: str, error: Exception) -> None:
        now = time.monotonic()
        self._down_until = now + BACKEND_RETRY_INTERVAL
        if now - self._error_logged_at > 30:
            self._error_logged_at = now
            self.logger.warning(f"State backend {action} failed (continuing locally, "
                                f"retrying in {BACKEND_RETRY_INTERVAL:g}s): {error}")
