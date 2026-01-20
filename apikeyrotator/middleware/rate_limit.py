"""
Middleware for rate-limiting management
"""

import time
import asyncio
import logging
import random
import threading
from typing import Dict, Any, Optional
from .models import RequestInfo, ResponseInfo, ErrorInfo


class RateLimitMiddleware:
    """
    Middleware for tracking rate limits.
    """

    def __init__(
        self,
        pause_on_limit: bool = True,
        max_tracked_keys: int = 1000,
        logger: Optional[logging.Logger] = None
    ):
        """
        Args:
            pause_on_limit: Whether to wait until rate limit expires
            max_tracked_keys: Maximum number of tracked keys
            logger: Logger for output messages
        """
        self.rate_limits: Dict[str, Dict[str, Any]] = {}
        self.pause_on_limit = pause_on_limit
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

    def _get_header_nocase(self, headers: Dict[str, str], key: str) -> Optional[str]:
        """Helper to get header value ignoring case."""
        if not headers:
            return None
        # Direct lookup first (fastest)
        if key in headers:
            return headers[key]
        # Case-insensitive lookup
        key_lower = key.lower()
        for k, v in headers.items():
            if k.lower() == key_lower:
                return v
        return None

    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        """
        Checks rate limit before request.
        """
        key = request_info.key
        wait_time = 0.0

        with self._lock:
            # Periodic cleanup (every 50 requests)
            self._request_count += 1
            if self._request_count % 50 == 0:
                self._cleanup_expired()
                self._evict_oldest()

            if key in self.rate_limits:
                limit_info = self.rate_limits[key]
                reset_time = limit_info.get('reset_time', 0)

                if self.pause_on_limit and reset_time > time.time():
                    wait_time = reset_time - time.time()

                    jitter = random.uniform(0, wait_time * 0.1)
                    wait_time += jitter

                    self.logger.warning(
                        f"⏸️ Rate limit for key {key[:4]}****. Waiting {wait_time:.1f}s "
                        f"(remaining={limit_info.get('remaining', '?')})"
                    )

        # Wait outside lock to avoid blocking other requests
        if wait_time > 0:
            await asyncio.sleep(wait_time)

        return request_info

    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        """
        Extracts rate-limit information from headers (Case-Insensitive).
        """
        key = response_info.request_info.key
        headers = response_info.headers

        rate_limit_info = {}

        # Standard rate-limit headers
        limit = self._get_header_nocase(headers, 'X-RateLimit-Limit')
        if limit:
            try:
                rate_limit_info['limit'] = int(limit)
            except (ValueError, TypeError):
                pass

        remaining = self._get_header_nocase(headers, 'X-RateLimit-Remaining')
        if remaining:
            try:
                rate_limit_info['remaining'] = int(remaining)
            except (ValueError, TypeError):
                pass

        reset = self._get_header_nocase(headers, 'X-RateLimit-Reset')
        if reset:
            try:
                rate_limit_info['reset_time'] = int(reset)
            except (ValueError, TypeError):
                pass

        # Alternative header names (no prefix)
        if 'limit' not in rate_limit_info:
            limit = self._get_header_nocase(headers, 'RateLimit-Limit')
            if limit:
                try:
                    rate_limit_info['limit'] = int(limit)
                except (ValueError, TypeError): pass

        if 'remaining' not in rate_limit_info:
            remaining = self._get_header_nocase(headers, 'RateLimit-Remaining')
            if remaining:
                try:
                    rate_limit_info['remaining'] = int(remaining)
                except (ValueError, TypeError): pass

        if 'reset_time' not in rate_limit_info:
            reset = self._get_header_nocase(headers, 'RateLimit-Reset')
            if reset:
                try:
                    rate_limit_info['reset_time'] = int(reset)
                except (ValueError, TypeError): pass

        # Store if we found any rate limit info
        if rate_limit_info:
            with self._lock:
                if key not in self.rate_limits:
                    self._evict_oldest()

                # Update existing info or create new
                if key in self.rate_limits:
                    self.rate_limits[key].update(rate_limit_info)
                else:
                    self.rate_limits[key] = rate_limit_info

            self.logger.debug(
                f"Updated rate limit for key {key[:4]}****: "
                f"limit={rate_limit_info.get('limit', '?')}, "
                f"remaining={rate_limit_info.get('remaining', '?')}"
            )

        return response_info

    async def on_error(self, error_info: ErrorInfo) -> bool:
        """
        Handles rate limit errors (429).
        """
        if error_info.status_code == 429:
            key = error_info.request_info.key
            headers = error_info.headers or {}

            # Try to extract Retry-After header
            retry_after = self._get_header_nocase(headers, 'Retry-After')
            reset_time = None

            if retry_after:
                try:
                    # Retry-After can be seconds or HTTP date
                    reset_time = time.time() + int(retry_after)
                except (ValueError, TypeError):
                    pass

            # Fallback to X-RateLimit-Reset
            if not reset_time:
                reset_val = self._get_header_nocase(headers, 'X-RateLimit-Reset')
                if reset_val:
                    try:
                        reset_time = int(reset_val)
                    except (ValueError, TypeError):
                        pass

            # Default: wait 60 seconds
            if not reset_time:
                reset_time = time.time() + 60

            with self._lock:
                if key not in self.rate_limits:
                    self._evict_oldest()

                self.rate_limits[key] = {
                    'reset_time': reset_time,
                    'remaining': 0
                }

            self.logger.warning(
                f"⚠️ Rate limit hit for key {key[:4]}****. "
                f"Reset at {reset_time}"
            )

        return True  # Continue with retry logic

    def get_stats(self) -> Dict[str, Any]:
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