"""
Middleware for caching
"""

import time
import hashlib
import json
import logging
import sys
import threading
from typing import Dict, Any, Optional
from collections import OrderedDict
from .models import RequestInfo, ResponseInfo, ErrorInfo


class CachingMiddleware:
    """
    Middleware for caching GET requests.

    """

    def __init__(
        self,
        ttl: int = 300,
        cache_only_get: bool = True,
        max_cache_size: int = 1000,
        max_cache_size_bytes: int = 100 * 1024 * 1024,  # FIXED #2: 100MB default
        max_cacheable_size: int = 10 * 1024 * 1024,  # FIXED #7: 10MB per response
        logger: Optional[logging.Logger] = None
    ):
        """
        Args:
            ttl: Cache lifetime in seconds
            cache_only_get: Cache only GET requests
            max_cache_size: Maximum cache size (number of entries)
            max_cache_size_bytes: Maximum total cache size in bytes (FIXED #2)
            max_cacheable_size: Maximum size per response in bytes (FIXED #7)
            logger: Logger for output messages
        """
        # FIXED: OrderedDict for LRU eviction
        self.cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.ttl = ttl
        self.cache_only_get = cache_only_get
        self.max_cache_size = max(1, max_cache_size)
        self.max_cache_size_bytes = max_cache_size_bytes  # FIXED #2
        self.max_cacheable_size = max_cacheable_size  # FIXED #7

        self.logger = logger if logger else logging.getLogger(__name__)

        # Thread-safety
        self._lock = threading.RLock()

        # Statistics
        self.hits = 0
        self.misses = 0

        self.logger.info(
            f"CachingMiddleware initialized: TTL={ttl}s, "
            f"max_entries={self.max_cache_size}, max_bytes={max_cache_size_bytes}, "
            f"max_per_response={max_cacheable_size}, GET_only={cache_only_get}"
        )

    def _get_response_size(self, response_info: ResponseInfo) -> int:
        """Calculate approximate size of cached response in bytes"""
        size = 0
        if response_info.content:
            # Use len() for accurate content size, not sys.getsizeof()
            size += len(response_info.content)
        if response_info.headers:
            size += len(str(response_info.headers))
        return size

    def _get_total_cache_size(self) -> int:
        """Get total size of all cached responses in bytes"""
        total = 0
        for cached in self.cache.values():
            if 'response' in cached:
                total += self._get_response_size(cached['response'])
        return total

    def _is_safe_to_cache(self, response_info: ResponseInfo) -> bool:
        """
        Validates if response is safe to cache (prevents cache poisoning).

        Args:
            response_info: Response information

        Returns:
            bool: True if safe to cache
        """
        # Don't cache if response contains Set-Cookie (auth/session data)
        if 'Set-Cookie' in response_info.headers or 'set-cookie' in response_info.headers:
            self.logger.debug("Not caching: response contains Set-Cookie header")
            return False

        # Don't cache if Content-Type indicates non-cacheable content
        content_type = response_info.headers.get('Content-Type', '').lower()
        non_cacheable_types = [
            'text/event-stream',  # Server-sent events
            'multipart/x-mixed-replace',  # Live streams
        ]
        if any(ct in content_type for ct in non_cacheable_types):
            self.logger.debug(f"Not caching: non-cacheable Content-Type: {content_type}")
            return False

        # Don't cache if Cache-Control explicitly forbids it
        cache_control = response_info.headers.get('Cache-Control', '').lower()
        if 'no-store' in cache_control or 'private' in cache_control:
            self.logger.debug(f"Not caching: Cache-Control forbids: {cache_control}")
            return False

        # Don't cache very large responses (potential DoS)
        response_size = self._get_response_size(response_info)
        if response_size > self.max_cacheable_size:
            self.logger.warning(
                f"Not caching: response too large ({response_size} bytes, "
                f"max: {self.max_cacheable_size})"
            )
            return False

        # Don't cache if URL contains sensitive patterns
        url = response_info.request_info.url.lower()
        sensitive_patterns = ['/login', '/auth', '/password', '/token', '/session']
        if any(pattern in url for pattern in sensitive_patterns):
            self.logger.debug(f"Not caching: URL contains sensitive pattern")
            return False

        return True

    def _get_cache_key(self, request_info: RequestInfo) -> str:
        """
        Args:
            request_info: Request information

        Returns:
            str: Hash to use as cache key
        """
        # Base key: method + URL
        key_parts = [
            request_info.method.upper(),
            request_info.url,
        ]

        # Add relevant headers (excluding Authorization)
        relevant_headers = {
            k: v for k, v in request_info.headers.items()
            if k.lower() not in ['authorization', 'x-api-key', 'user-agent', 'cookie']
        }
        if relevant_headers:
            key_parts.append(json.dumps(relevant_headers, sort_keys=True))

        # For POST/PUT include request body
        if request_info.method.upper() in ['POST', 'PUT', 'PATCH']:
            body = request_info.kwargs.get('json') or request_info.kwargs.get('data')
            if body:
                try:
                    body_str = json.dumps(body, sort_keys=True) if isinstance(body, dict) else str(body)
                    key_parts.append(body_str)
                except (TypeError, ValueError):
                    # If we can't serialize, use repr
                    key_parts.append(repr(body))

        # Hash for compactness
        cache_key = hashlib.sha256('|'.join(key_parts).encode()).hexdigest()
        return cache_key

    def _evict_expired(self):
        """
        Called periodically to prevent memory leaks.
        """
        current_time = time.time()
        expired_keys = []

        for key, cached in self.cache.items():
            if current_time - cached['timestamp'] >= self.ttl:
                expired_keys.append(key)

        for key in expired_keys:
            del self.cache[key]

        if expired_keys:
            self.logger.debug(f"Evicted {len(expired_keys)} expired cache entries")

    def _evict_lru(self):
        """Remove oldest item to make space"""
        if len(self.cache) > 0:
            removed_key, _ = self.cache.popitem(last=False)
            self.logger.debug(f"LRU eviction: removed cache entry {removed_key[:16]}...")

    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        """
        Checks cache before request.
        """
        if self.cache_only_get and request_info.method.upper() != 'GET':
            return request_info

        cache_key = self._get_cache_key(request_info)

        with self._lock:
            # Periodic cleanup (every 100 requests)
            if (self.hits + self.misses) % 100 == 0:
                self._evict_expired()

            if cache_key in self.cache:
                cached = self.cache[cache_key]
                if time.time() - cached['timestamp'] < self.ttl:
                    self.hits += 1
                    # Move to end for LRU
                    self.cache.move_to_end(cache_key)
                    self.logger.info(
                        f"✅ Cache HIT for {request_info.method} {request_info.url} "
                        f"(hit_rate={self.hits/(self.hits+self.misses):.2%})"
                    )
                    # TODO: Can return cached response directly
                    # But that requires support in rotator
                else:
                    # Expired cache
                    del self.cache[cache_key]
                    self.misses += 1
            else:
                self.misses += 1
                self.logger.debug(f"Cache MISS for {request_info.method} {request_info.url}")

        return request_info

    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        """
        Caches successful responses.
        """
        if self.cache_only_get and response_info.request_info.method.upper() != 'GET':
            return response_info

        if 200 <= response_info.status_code < 300:

            if not self._is_safe_to_cache(response_info):
                return response_info

            cache_key = self._get_cache_key(response_info.request_info)
            response_size = self._get_response_size(response_info)

            with self._lock:
                is_new_key = cache_key not in self.cache

                if is_new_key:
                    # Evict by entry count
                    while len(self.cache) >= self.max_cache_size:
                        self._evict_lru()

                    while self._get_total_cache_size() + response_size > self.max_cache_size_bytes:
                        if len(self.cache) == 0:
                            # Cache is empty but response is too large
                            self.logger.warning(
                                f"Response too large to cache: {response_size} bytes "
                                f"(limit: {self.max_cache_size_bytes})"
                            )
                            return response_info
                        self._evict_lru()

                self.cache[cache_key] = {
                    'response': response_info,
                    'timestamp': time.time()
                }

            self.logger.debug(
                f"💾 Cached response for {response_info.request_info.url} "
                f"(size={response_size} bytes, cache_size={len(self.cache)}/{self.max_cache_size}, "
                f"total_bytes={self._get_total_cache_size()}/{self.max_cache_size_bytes})"
            )

        return response_info

    async def on_error(self, error_info: ErrorInfo) -> bool:
        """Errors are not cached"""
        return False

    def clear_cache(self):
        """Clears entire cache"""
        with self._lock:
            self.cache.clear()
            self.hits = 0
            self.misses = 0
        self.logger.info("Cache cleared")

    def get_stats(self) -> Dict[str, Any]:
        """Returns cache statistics"""
        with self._lock:
            total = self.hits + self.misses
            hit_rate = self.hits / total if total > 0 else 0.0
            total_size = self._get_total_cache_size()

            return {
                "cache_size": len(self.cache),
                "max_cache_size": self.max_cache_size,
                "total_bytes": total_size,
                "max_bytes": self.max_cache_size_bytes,
                "max_per_response": self.max_cacheable_size,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": hit_rate,
                "total_requests": total,
            }