"""
Middleware for rate-limiting management
"""

import time
import asyncio
import logging
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

        # FIXED: Logger instead of print
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

    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        """
        Checks rate limit before request.
        """
        key = request_info.key
        wait_time = 0.0  # Initialize wait_time

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
        Extracts rate-limit information from headers.
        """
        key = response_info.request_info.key
        headers = response_info.headers

        rate_limit_info = {}

        # Standard rate-limit headers
        if 'X-RateLimit-Limit' in headers:
            try:
                rate_limit_info['limit'] = int(headers['X-RateLimit-Limit'])
            except ValueError:
                pass

        if 'X-RateLimit-Remaining' in headers:
            try:
                rate_limit_info['remaining'] = int(headers['X-RateLimit-Remaining'])
            except ValueError:
                pass

        if 'X-RateLimit-Reset' in headers:
            try:
                rate_limit_info['reset_time'] = int(headers['X-RateLimit-Reset'])
            except ValueError:
                pass

        if 'Retry-After' in headers:
            retry_after = headers['Retry-After']
            try:
                if retry_after.isdigit():
                    rate_limit_info['reset_time'] = time.time() + int(retry_after)
                else:
                    # May be HTTP date
                    from email.utils import parsedate_to_datetime
                    rate_limit_info['reset_time'] = parsedate_to_datetime(retry_after).timestamp()
            except (ValueError, TypeError):
                pass

        if rate_limit_info:
            with self._lock:
                # Check limit before adding
                if len(self.rate_limits) >= self.max_tracked_keys:
                    self._evict_oldest()

                self.rate_limits[key] = rate_limit_info

                self.logger.debug(
                    f"Updated rate limit for key {key[:4]}****: "
                    f"remaining={rate_limit_info.get('remaining', '?')}"
                )

        return response_info

    async def on_error(self, error_info: ErrorInfo) -> bool:
        """
        Handles 429 (Too Many Requests) errors.

        """
        if error_info.response_info and error_info.response_info.status_code == 429:
            key = error_info.request_info.key
            self.logger.warning(f"⚠️ Rate limit (429) hit for key {key[:4]}****")

            with self._lock:
                if 'Retry-After' in error_info.response_info.headers:
                    try:
                        retry_after = int(error_info.response_info.headers['Retry-After'])
                        self.rate_limits[key] = {'reset_time': time.time() + retry_after}
                        self.logger.info(f"Will retry after {retry_after}s")
                    except ValueError:
                        self.rate_limits[key] = {'reset_time': time.time() + 60}
                else:
                    # Default: wait 60 seconds
                    self.rate_limits[key] = {'reset_time': time.time() + 60}

            return True
        return False

    def get_stats(self) -> Dict[str, Any]:
        """Returns rate-limiting statistics"""
        with self._lock:
            active_limits = sum(
                1 for info in self.rate_limits.values()
                if info.get('reset_time', 0) > time.time()
            )

            return {
                "tracked_keys": len(self.rate_limits),
                "max_tracked_keys": self.max_tracked_keys,
                "active_limits": active_limits,
            }

    def clear_limits(self):
        """Clears all rate-limit records"""
        with self._lock:
            self.rate_limits.clear()
        self.logger.info("All rate limits cleared")