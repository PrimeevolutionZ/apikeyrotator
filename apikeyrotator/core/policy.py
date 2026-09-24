"""Retry policy: how many attempts, how long to wait, what may be retried, time budgets."""

from __future__ import annotations
import random
import time
from collections.abc import Callable
from typing import Any

from apikeyrotator.utils import get_header


DEFAULT_MAX_DELAY = 60.0

#: RFC 9110 idempotent methods - safe to retry after any failure
IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE", "TRACE"})
#: Statuses meaning "the request was not processed" - safe to retry even for POST/PATCH
NON_IDEMPOTENT_RETRYABLE_STATUSES = frozenset({408, 425, 429, 503})


class RetryPolicy:
    """
    Attempts, backoff and timeouts of one request.

    Pure decisions without I/O - the request engine asks, the drivers wait.
    """

    __slots__ = ('max_retries', 'base_delay', 'max_delay', 'timeout', 'total_timeout',
                 'retry_non_idempotent', 'should_retry_callback', 'random_delay_range')

    def __init__(
            self,
            max_retries: int = 3,
            base_delay: float = 1.0,
            max_delay: float = DEFAULT_MAX_DELAY,
            timeout: float = 10.0,
            total_timeout: float | None = None,
            retry_non_idempotent: bool = False,
            should_retry_callback: Callable[[Any], bool] | None = None,
            random_delay_range: tuple[float, float] | None = None,
    ):
        if max_retries < 1:
            raise ValueError("max_retries must be >= 1")
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.timeout = timeout
        self.total_timeout = total_timeout
        self.retry_non_idempotent = retry_non_idempotent
        self.should_retry_callback = should_retry_callback
        self.random_delay_range = random_delay_range

    def is_idempotent(self, method_upper: str, headers: Any) -> bool:
        """May the request be retried after the server possibly processed it?"""
        return (
            self.retry_non_idempotent
            or method_upper in IDEMPOTENT_METHODS
            or get_header(headers, "Idempotency-Key") is not None
        )

    @staticmethod
    def may_retry_status(idempotent: bool, status_code: int) -> bool:
        return idempotent or status_code in NON_IDEMPOTENT_RETRYABLE_STATUSES

    def deadline(self, total_timeout: float | None) -> float | None:
        """Monotonic deadline for a request (None = no limit)."""
        return time.monotonic() + total_timeout if total_timeout is not None else None

    def backoff(self, attempt: int) -> float:
        # Cap the exponent too, to avoid float overflow for huge max_retries
        delay = min(self.base_delay * (2 ** min(attempt, 30)), self.max_delay)
        return min(delay + random.uniform(0, delay * 0.1), self.max_delay)

    def random_delay(self) -> float:
        low_high = self.random_delay_range
        if not low_high:
            return 0.0
        delay = random.uniform(low_high[0], low_high[1])
        return delay + random.uniform(0, delay * 0.1)

    def attempt_timeout(self, user_timeout: Any, remaining: float | None) -> float | None:
        """Per-attempt timeout: the user's (or default) timeout, clipped to the remaining budget."""
        if user_timeout is None:
            timeout = self.timeout
        elif isinstance(user_timeout, (int, float)):
            timeout = float(user_timeout)
        else:
            return None  # library-specific timeout object - passed through as is
        if remaining is not None:
            timeout = min(timeout, max(remaining, 0.001))
        return timeout
