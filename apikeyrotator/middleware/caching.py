"""Middleware для кэширования"""

import time
from typing import Dict, Any
from .models import RequestInfo, ResponseInfo, ErrorInfo


class CachingMiddleware:
    """Middleware для кэширования GET запросов"""

    def __init__(self, ttl: int = 300, cache_only_get: bool = True):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.ttl = ttl
        self.cache_only_get = cache_only_get

    def _get_cache_key(self, request_info: RequestInfo) -> str:
        return f"{request_info.method}:{request_info.url}"

    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        if self.cache_only_get and request_info.method.upper() != 'GET':
            return request_info

        cache_key = self._get_cache_key(request_info)
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            if time.time() - cached['timestamp'] < self.ttl:
                print(f"✅ Cache hit for {request_info.url}")
        return request_info

    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        if self.cache_only_get and response_info.request_info.method.upper() != 'GET':
            return response_info

        if 200 <= response_info.status_code < 300:
            cache_key = self._get_cache_key(response_info.request_info)
            self.cache[cache_key] = {
                'response': response_info,
                'timestamp': time.time()
            }
            print(f"💾 Cached response for {response_info.request_info.url}")
        return response_info

    async def on_error(self, error_info: ErrorInfo) -> bool:
        return False

    def clear_cache(self):
        """Очищает весь кэш"""
        self.cache.clear()
