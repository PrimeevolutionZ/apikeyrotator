"""
Middleware for caching
"""
import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from typing import Any

from .base import RotatorMiddleware
from .models import RequestInfo, ResponseInfo


class CachingMiddleware(RotatorMiddleware):
    """
    Middleware for caching GET requests.
    Thread-safe and supports both Sync/Async.
    """

    def __init__(
        self,
        ttl: int = 300,
        cache_only_get: bool = True,
        max_cache_size: int = 1000,
        max_cache_size_bytes: int = 100 * 1024 * 1024,
        max_cacheable_size: int = 10 * 1024 * 1024,
        logger: logging.Logger | None = None
    ):
        self.cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self.ttl = ttl
        self.cache_only_get = cache_only_get
        self.max_cache_size = max(1, max_cache_size)
        self.max_cache_size_bytes = max_cache_size_bytes
        self.max_cacheable_size = max_cacheable_size
        self.logger = logger if logger else logging.getLogger(__name__)
        self._lock = threading.RLock()
        self.hits = 0
        self.misses = 0
        # Running total of cached bytes - avoids an O(n) scan on every insert
        self._current_size_bytes = 0
        self._ops_since_cleanup = 0

    def _get_response_size(self, response_info: ResponseInfo) -> int:
        size = 0
        content = response_info.content
        if content:
            try:
                size += len(content)
            except TypeError:
                size += len(str(content))
        if response_info.headers:
            size += len(str(response_info.headers))
        return size

    def _get_total_cache_size(self) -> int:
        with self._lock:
            return self._current_size_bytes

    @staticmethod
    def _header(headers: dict[str, Any], name: str) -> str:
        if not headers:
            return ''
        name_lower = name.lower()
        for k, v in headers.items():
            if isinstance(k, str) and k.lower() == name_lower:
                return str(v)
        return ''

    def _is_safe_to_cache(self, response_info: ResponseInfo) -> bool:
        headers = response_info.headers or {}
        if self._header(headers, 'Set-Cookie'):
            return False
        content_type = self._header(headers, 'Content-Type').lower()
        if any(ct in content_type for ct in ['text/event-stream', 'multipart/x-mixed-replace']):
            return False
        cache_control = self._header(headers, 'Cache-Control').lower()
        if 'no-store' in cache_control or 'private' in cache_control:
            return False
        if self._get_response_size(response_info) > self.max_cacheable_size:
            return False
        return True

    @staticmethod
    def _stable_repr(value: Any) -> str:
        try:
            return json.dumps(value, sort_keys=True, default=str)
        except (TypeError, ValueError):
            return repr(value)

    def _get_cache_key(self, request_info: RequestInfo) -> str:
        key_parts = [request_info.method.upper(), request_info.url]
        relevant_headers = {
            k: v for k, v in (request_info.headers or {}).items()
            if k.lower() not in ['authorization', 'x-api-key', 'user-agent', 'cookie']
        }
        if relevant_headers:
            key_parts.append(json.dumps(relevant_headers, sort_keys=True, default=str))
        kwargs = request_info.kwargs or {}
        # Query parameters passed separately from the URL must be part of the key,
        # otherwise GET /search?q=a and ?q=b would share one cache entry.
        params = kwargs.get('params')
        if params:
            key_parts.append('params=' + self._stable_repr(params))
        if request_info.method.upper() in ['POST', 'PUT', 'PATCH']:
            body = kwargs.get('json')
            if body is None:
                body = kwargs.get('data')
            if body is not None:
                key_parts.append('body=' + self._stable_repr(body))
        return hashlib.sha256('|'.join(key_parts).encode()).hexdigest()

    def _delete_entry(self, cache_key: str) -> None:
        entry = self.cache.pop(cache_key, None)
        if entry is not None:
            self._current_size_bytes -= entry.get('size', 0)

    def _evict_expired(self):
        current_time = time.time()
        expired_keys = [k for k, v in self.cache.items() if current_time - v['timestamp'] >= self.ttl]
        for key in expired_keys:
            self._delete_entry(key)

    def _evict_lru(self):
        if len(self.cache) > 0:
            _, entry = self.cache.popitem(last=False)
            self._current_size_bytes -= entry.get('size', 0)

    def clear(self) -> None:
        """Removes all cached entries."""
        with self._lock:
            self.cache.clear()
            self._current_size_bytes = 0

    # --- Sync Implementation ---

    def before_request_sync(self, request_info: RequestInfo) -> RequestInfo | ResponseInfo:
        if self.cache_only_get and request_info.method.upper() != 'GET':
            return request_info

        cache_key = self._get_cache_key(request_info)
        with self._lock:
            self._ops_since_cleanup += 1
            if self._ops_since_cleanup >= 100:
                self._ops_since_cleanup = 0
                self._evict_expired()

            cached = self.cache.get(cache_key)
            if cached is not None:
                if time.time() - cached['timestamp'] < self.ttl:
                    self.hits += 1
                    self.cache.move_to_end(cache_key)
                    self.logger.debug(f"Cache HIT for {request_info.url}")
                    cached_response: ResponseInfo = cached['response']
                    return cached_response
                self._delete_entry(cache_key)
            self.misses += 1
        return request_info

    def after_request_sync(self, response_info: ResponseInfo) -> ResponseInfo:
        if self.cache_only_get and response_info.request_info.method.upper() != 'GET':
            return response_info

        if 200 <= response_info.status_code < 300:
            if not self._is_safe_to_cache(response_info):
                return response_info

            cache_key = self._get_cache_key(response_info.request_info)
            response_size = self._get_response_size(response_info)
            if response_size > self.max_cache_size_bytes:
                return response_info

            with self._lock:
                self._delete_entry(cache_key)
                while len(self.cache) >= self.max_cache_size:
                    self._evict_lru()
                while self.cache and self._current_size_bytes + response_size > self.max_cache_size_bytes:
                    self._evict_lru()

                self.cache[cache_key] = {
                    'response': response_info,
                    'timestamp': time.time(),
                    'size': response_size,
                }
                self._current_size_bytes += response_size
        return response_info

    # --- Async Hooks ---

    async def before_request(self, request_info: RequestInfo) -> RequestInfo | ResponseInfo:
        return self.before_request_sync(request_info)

    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        return self.after_request_sync(response_info)

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            total = self.hits + self.misses
            return {
                "cache_size": len(self.cache),
                "hits": self.hits,
                "misses": self.misses,
                "total": total,
                "hit_rate": self.hits / total if total else 0.0,
                "size_bytes": self._current_size_bytes,
            }