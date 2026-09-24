"""Client-side rate limiting: token buckets per key and rate-limit response headers."""

from __future__ import annotations
import time
from typing import Any

from apikeyrotator.utils import parse_rate_limit_headers, parse_retry_after

from .keys import KeyPool
from .policy import RetryPolicy
from .shared_state import Report, StateSync


class RateLimiter:
    """
    Decides when a key may be used again.

    - ``key_rate_limit=(n, seconds)``: token bucket per key (in the state backend,
      so it is shared between processes when the backend is).
    - 429 responses and ``X-RateLimit-Remaining: 0`` park the key until its reset.
    """

    __slots__ = ('pool', 'state', 'policy', 'key_rate_limit', '_capacity', '_refill',
                 'respect_headers')

    def __init__(self, pool: KeyPool, state: StateSync, policy: RetryPolicy,
                 key_rate_limit: tuple[int, float] | None, respect_headers: bool):
        if key_rate_limit is not None:
            requests_count, per_seconds = key_rate_limit
            if requests_count < 1 or per_seconds <= 0:
                raise ValueError("key_rate_limit must be (requests >= 1, per_seconds > 0)")
            self._capacity = int(requests_count)
            self._refill = requests_count / float(per_seconds)
        else:
            self._capacity, self._refill = 0, 0.0
        self.key_rate_limit = key_rate_limit
        self.pool = pool
        self.state = state
        self.policy = policy
        self.respect_headers = respect_headers

    # --- token bucket ---

    def bucket_wait(self, key: str) -> float:
        """Takes a token for `key`; returns seconds to wait (0 = acquired)."""
        return self.state.acquire_token(key, self._capacity, self._refill)

    def after_bucket_denied(self, key: str, wait: float) -> float:
        """Parks `key` locally; returns how long to sleep before selecting again (0 = another key is free)."""
        pool = self.pool
        pool.mark_rate_limited(key, time.time() + wait)
        if pool.has_available_key():
            return 0.0
        until_free = pool.time_until_key_available()
        return min(until_free if until_free is not None else wait, self.policy.max_delay)

    # --- server feedback ---

    def mark(self, reports: list[Report], key: str, until: float) -> None:
        self.pool.mark_rate_limited(key, until)
        self.state.report_rate_limited(reports, key, until)

    def on_rate_limited(self, reports: list[Report], key: str, headers: Any, attempt: int) -> None:
        """429: park the key for Retry-After / X-RateLimit-Reset (or a backoff if absent)."""
        retry_after = parse_retry_after(headers)
        if retry_after is None:
            _, reset = parse_rate_limit_headers(headers)
            if reset is not None:
                retry_after = max(0.0, reset - time.time())
        if retry_after is None:
            retry_after = self.policy.backoff(attempt)
        self.mark(reports, key, time.time() + retry_after)

    def on_success(self, reports: list[Report], key: str, headers: Any) -> None:
        """Proactive limiting: `Remaining: 0` means the next request with this key would get 429."""
        if not self.respect_headers:
            return
        remaining, reset = parse_rate_limit_headers(headers)
        if remaining is not None and remaining <= 0 and reset is not None and reset > time.time():
            self.mark(reports, key, reset)

    def wait_after_rate_limit(self, backoff: float) -> float:
        """Switch to another key immediately; if all are limited, wait for the earliest one."""
        pool = self.pool
        if pool.has_available_key():
            return 0.0
        wait = pool.time_until_key_available()
        if wait is not None:
            return min(max(wait, 0.0), self.policy.max_delay)
        return backoff
