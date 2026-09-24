"""
Middleware for rate-limiting management
"""

import asyncio
import logging
import random
import threading
import time
from typing import Any

from ..utils.error_classifier import get_header, parse_retry_after, rate_limit_header_values
from .base import RotatorMiddleware
from .models import ErrorInfo, RequestInfo, ResponseInfo


class RateLimitMiddleware(RotatorMiddleware):
    """
    Middleware for tracking rate limits.
    """

    def __init__(
        self,
        pause_on_limit: bool = True,
        max_tracked_keys: int = 1000,
        logger: logging.Logger | None = None,
        max_wait: float = 300.0
    ):
        """
        Args:
            pause_on_limit: Whether to wait until rate limit expires
            max_tracked_keys: Maximum number of tracked keys
            logger: Logger for output messages
            max_wait: Upper bound (seconds) for a single pause
        """
        self.rate_limits: dict[str, dict[str, Any]] = {}
        self.pause_on_limit = pause_on_limit
        self.max_wait = max(0.0, max_wait)
        self.max_tracked_keys = max(10, max_tracked_keys)

        self.logger = logger if logger else logging.getLogger(__name__)

        # Thread-safety
        self._lock = threading.RLock()

        # Counter for periodic cleanup
        self._request_count = 0

        self.logger.info(
            f"RateLimitMiddleware initialized: pause_on_limit={pause_on_limit}, "
            f"max_tracked_keys={self.max_tracked_keys}"
        )

    def _cleanup_expired(self):
        current_time = time.time()
        expired_keys = []

        for key, limit_info in self.rate_limits.items():
            reset_time = limit_info.get('reset_time', 0)
            # Remove if reset was more than 1 hour ago
            if reset_time > 0 and reset_time < current_time - 3600:
                expired_keys.append(key)

        for key in expired_keys:
            del self.rate_limits[key]

        if expired_keys:
            self.logger.debug(f"Cleaned up {len(expired_keys)} expired rate limit entries")

    def _evict_oldest(self):
        if len(self.rate_limits) >= self.max_tracked_keys:
            # Sort by reset_time and remove oldest
            sorted_keys = sorted(
                self.rate_limits.items(),
                key=lambda x: x[1].get('reset_time', 0)
            )

            # Remove 10% oldest
            to_remove = max(1, len(sorted_keys) // 10)
            for key, _ in sorted_keys[:to_remove]:
                del self.rate_limits[key]

            self.logger.debug(f"Evicted {to_remove} oldest rate limit entries")

    # Values below this are treated as "seconds until reset", larger values as UNIX timestamps
    _EPOCH_THRESHOLD = 1_000_000_000

    def _get_header_nocase(self, headers: dict[str, str], key: str) -> str | None:
        """Helper to get header value ignoring case."""
        return get_header(headers, key)

    @staticmethod
    def _parse_number(value: str | None) -> float | None:
        if value is None:
            return None
        try:
            # Some APIs send lists like "100, 100;w=60" - take the first value
            return float(str(value).split(',')[0].split(';')[0].strip())
        except (ValueError, TypeError):
            return None

    @classmethod
    def _to_reset_timestamp(cls, value: float, now: float | None = None) -> float:
        """Normalizes a reset value (delta seconds or UNIX timestamp) to a UNIX timestamp."""
        if now is None:
            now = time.time()
        if value < cls._EPOCH_THRESHOLD:
            return now + max(0.0, value)
        return value

    def _extract_rate_limit_info(self, headers: dict[str, str]) -> dict[str, Any]:
        """Extract rate limit information from response headers (single pass)."""
        rate_limit_info: dict[str, Any] = {}
        limit_raw, remaining_raw, reset_raw = rate_limit_header_values(headers)

        limit = self._parse_number(limit_raw)
        if limit is not None:
            rate_limit_info['limit'] = int(limit)
        remaining = self._parse_number(remaining_raw)
        if remaining is not None:
            rate_limit_info['remaining'] = int(remaining)
        reset = self._parse_number(reset_raw)
        if reset is not None:
            rate_limit_info['reset_time'] = self._to_reset_timestamp(reset)

        return rate_limit_info

    def _store_rate_limit_info(self, key: str, rate_limit_info: dict[str, Any]) -> None:
        """Store rate limit info for a key."""
        if rate_limit_info:
            with self._lock:
                if key not in self.rate_limits:
                    self._evict_oldest()

                if key in self.rate_limits:
                    self.rate_limits[key].update(rate_limit_info)
                else:
                    self.rate_limits[key] = rate_limit_info

            self.logger.debug(
                f"Updated rate limit for key {key[:4]}****: "
                f"limit={rate_limit_info.get('limit', '?')}, "
                f"remaining={rate_limit_info.get('remaining', '?')}"
            )

    def _check_rate_limit(self, key: str) -> float:
        """Check if key is rate-limited and return wait time."""
        wait_time = 0.0

        with self._lock:
            self._request_count += 1
            if self._request_count % 50 == 0:
                self._cleanup_expired()
                self._evict_oldest()

            if key in self.rate_limits:
                limit_info = self.rate_limits[key]
                reset_time = limit_info.get('reset_time', 0)

                # Pause only when the quota is actually used up. The reset header is
                # present on every response, so reset_time alone doesn't mean "blocked".
                remaining = limit_info.get('remaining', 1)
                if self.pause_on_limit and remaining <= 0 and reset_time > time.time():
                    wait_time = min(reset_time - time.time(), self.max_wait)
                    jitter = random.uniform(0, wait_time * 0.1)
                    wait_time += jitter

                    self.logger.warning(
                        f"Rate limit for key {key[:4]}****. Waiting {wait_time:.1f}s "
                        f"(remaining={limit_info.get('remaining', '?')})"
                    )

        return wait_time

    def _handle_error(self, error_info: ErrorInfo) -> bool:
        """Common error handling logic for rate limit errors (429)."""
        # Extract status code from response_info if available
        status_code = None
        headers = {}
        if error_info.response_info is not None:
            status_code = error_info.response_info.status_code
            headers = error_info.response_info.headers or {}

        if status_code == 429:
            key = error_info.request_info.key

            # Retry-After (seconds or HTTP-date), then X-RateLimit-Reset, then default 60s
            reset_time = None
            retry_after = parse_retry_after(headers)
            if retry_after is not None:
                reset_time = time.time() + retry_after

            if reset_time is None:
                reset_val = self._parse_number(self._get_header_nocase(headers, 'X-RateLimit-Reset'))
                if reset_val is None:
                    reset_val = self._parse_number(self._get_header_nocase(headers, 'RateLimit-Reset'))
                if reset_val is not None:
                    reset_time = self._to_reset_timestamp(reset_val)

            if reset_time is None:
                reset_time = time.time() + 60

            with self._lock:
                if key not in self.rate_limits:
                    self._evict_oldest()

                self.rate_limits[key] = {
                    'reset_time': reset_time,
                    'remaining': 0
                }

            self.logger.warning(
                f"Rate limit hit for key {key[:4]}****. "
                f"Reset at {reset_time}"
            )

        return True

    # --- Sync Hooks ---

    def before_request_sync(self, request_info: RequestInfo) -> RequestInfo:
        """Sync hook: checks rate limit before request."""
        wait_time = self._check_rate_limit(request_info.key)
        if wait_time > 0:
            time.sleep(wait_time)
        return request_info

    def after_request_sync(self, response_info: ResponseInfo) -> ResponseInfo:
        """Sync hook: extracts rate-limit information from headers."""
        key = response_info.request_info.key
        headers = response_info.headers
        rate_limit_info = self._extract_rate_limit_info(headers)
        self._store_rate_limit_info(key, rate_limit_info)
        return response_info

    def on_error_sync(self, error_info: ErrorInfo) -> bool:
        """Sync hook: handles rate limit errors."""
        return self._handle_error(error_info)

    # --- Async Hooks ---

    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        """Async hook: checks rate limit before request."""
        wait_time = self._check_rate_limit(request_info.key)
        if wait_time > 0:
            await asyncio.sleep(wait_time)
        return request_info

    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        """Async hook: extracts rate-limit information from headers."""
        key = response_info.request_info.key
        headers = response_info.headers
        rate_limit_info = self._extract_rate_limit_info(headers)
        self._store_rate_limit_info(key, rate_limit_info)
        return response_info

    async def on_error(self, error_info: ErrorInfo) -> bool:
        """Async hook: handles rate limit errors."""
        return self._handle_error(error_info)

    def get_stats(self) -> dict[str, Any]:
        """
        Returns statistics about tracked rate limits.
        """
        with self._lock:
            active_limits = sum(
                1 for info in self.rate_limits.values()
                if info.get('reset_time', 0) > time.time()
            )

            return {
                'tracked_keys': len(self.rate_limits),
                'active_limits': active_limits,
                'max_tracked_keys': self.max_tracked_keys
            }
