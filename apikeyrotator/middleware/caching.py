"""
Middleware for caching
"""

import time
import hashlib
import json
import logging
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
        logger: Optional[logging.Logger] = None
    ):
        """
        Args:
            ttl: Cache lifetime in seconds
            cache_only_get: Cache only GET requests
            max_cache_size: Maximum cache size (number of entries)
            logger: Logger for output messages
        """
        # FIXED: OrderedDict for LRU eviction
        self.cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.ttl = ttl
        self.cache_only_get = cache_only_get
        self.max_cache_size = max(1, max_cache_size)  # Changed minimum from 10 to 1

        self.logger = logger if logger else logging.getLogger(__name__)

        # Thread-safety
        self._lock = threading.RLock()

        # Statistics
        self.hits = 0
        self.misses = 0

        self.logger.info(
            f"CachingMiddleware initialized: TTL={ttl}s, "
            f"max_size={self.max_cache_size}, GET_only={cache_only_get}"
        )

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
        # Remove oldest item to make space
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
            cache_key = self._get_cache_key(response_info.request_info)

            with self._lock:
                # Check if we need to evict BEFORE adding
                # Only evict if this is a NEW key (not updating existing)
                if cache_key not in self.cache:
                    # When cache is at max size, evict one to make room for new entry
                    while len(self.cache) >= self.max_cache_size:
                        self._evict_lru()

                self.cache[cache_key] = {
                    'response': response_info,
                    'timestamp': time.time()
                }

            self.logger.debug(
                f"💾 Cached response for {response_info.request_info.url} "
                f"(cache_size={len(self.cache)}/{self.max_cache_size})"
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

            return {
                "cache_size": len(self.cache),
                "max_cache_size": self.max_cache_size,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": hit_rate,
                "total_requests": total,
            }