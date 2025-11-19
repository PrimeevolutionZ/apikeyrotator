"""
Middleware for retry logic management
"""

import asyncio
import logging
import threading
from typing import Dict, Optional
from .models import RequestInfo, ResponseInfo, ErrorInfo


class RetryMiddleware:
    """
    Middleware for managing retries.

    """

    def __init__(
        self,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
        max_tracked_urls: int = 1000,
        logger: Optional[logging.Logger] = None
    ):
        """
        Args:
            max_retries: Maximum number of retries
            backoff_factor: Multiplier for exponential backoff
            max_tracked_urls: Maximum tracked URLs
            logger: Logger for output messages
        """
        self.max_retries = max(1, max_retries)
        self.backoff_factor = max(1.0, backoff_factor)
        self.max_tracked_urls = max(1, max_tracked_urls)  # Changed minimum from 10 to 1

        self.retry_counts: Dict[str, int] = {}

        self.logger = logger if logger else logging.getLogger(__name__)

        # Thread-safety
        self._lock = threading.RLock()

        self.logger.info(
            f"RetryMiddleware initialized: max_retries={max_retries}, "
            f"backoff_factor={backoff_factor}, max_tracked_urls={max_tracked_urls}"
        )

    def _cleanup_successful(self, url: str):
        with self._lock:
            if url in self.retry_counts:
                del self.retry_counts[url]

    def _evict_oldest(self):
        with self._lock:
            if len(self.retry_counts) >= self.max_tracked_urls:
                # Remove 10% oldest (with lowest counter)
                to_remove = max(1, len(self.retry_counts) // 10)
                sorted_urls = sorted(
                    self.retry_counts.items(),
                    key=lambda x: x[1]
                )

                for url, _ in sorted_urls[:to_remove]:
                    del self.retry_counts[url]

                self.logger.debug(f"Evicted {to_remove} oldest retry entries")

    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        """Called before request"""
        return request_info

    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        url = response_info.request_info.url

        # Successful request - remove from tracking
        if 200 <= response_info.status_code < 300:
            self._cleanup_successful(url)

            with self._lock:
                if url in self.retry_counts:
                    retries = self.retry_counts[url]
                    self.logger.info(
                        f"✅ Request succeeded after {retries} retries: {url}"
                    )

        return response_info

    async def on_error(self, error_info: ErrorInfo) -> bool:
        url = error_info.request_info.url
        wait_time = 0.0

        with self._lock:
            retry_count = self.retry_counts.get(url, 0)

            if retry_count < self.max_retries:
                # Only evict if we're adding a NEW url and already at capacity
                if url not in self.retry_counts:
                    # When at max size, evict to make room for new URL
                    while len(self.retry_counts) >= self.max_tracked_urls:
                        self._evict_oldest()

                self.retry_counts[url] = retry_count + 1
                wait_time = self.backoff_factor ** retry_count

                self.logger.warning(
                    f"🔄 Retry {retry_count + 1}/{self.max_retries} for {url} "
                    f"after {wait_time:.1f}s (error: {type(error_info.exception).__name__})"
                )
            else:
                if url in self.retry_counts:
                    del self.retry_counts[url]

                self.logger.error(
                    f"❌ Max retries ({self.max_retries}) exhausted for {url}"
                )
                return False

        if wait_time > 0:
            await asyncio.sleep(wait_time)
            return True

        return False

    def get_stats(self) -> Dict[str, any]:
        """Returns retry statistics"""
        with self._lock:
            return {
                "tracked_urls": len(self.retry_counts),
                "max_tracked_urls": self.max_tracked_urls,
                "active_retries": sum(1 for count in self.retry_counts.values() if count > 0),
            }

    def clear_retries(self):
        """Clears all retry counters"""
        with self._lock:
            self.retry_counts.clear()
        self.logger.info("All retry counters cleared")