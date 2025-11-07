"""Middleware для управления rate limiting"""

import time
import asyncio
from typing import Dict, Any
from .models import RequestInfo, ResponseInfo, ErrorInfo


class RateLimitMiddleware:
    """Middleware для отслеживания rate limits"""

    def __init__(self, pause_on_limit: bool = True):
        self.rate_limits: Dict[str, Dict[str, Any]] = {}
        self.pause_on_limit = pause_on_limit

    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        key = request_info.key

        if key in self.rate_limits:
            limit_info = self.rate_limits[key]
            reset_time = limit_info.get('reset_time', 0)

            if self.pause_on_limit and reset_time > time.time():
                wait_time = reset_time - time.time()
                print(f"⏸️  Rate limit for key {key[:8]}... Waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)

        return request_info

    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        key = response_info.request_info.key
        headers = response_info.headers

        rate_limit_info = {}
        if 'X-RateLimit-Limit' in headers:
            rate_limit_info['limit'] = int(headers['X-RateLimit-Limit'])
        if 'X-RateLimit-Remaining' in headers:
            rate_limit_info['remaining'] = int(headers['X-RateLimit-Remaining'])
        if 'X-RateLimit-Reset' in headers:
            rate_limit_info['reset_time'] = int(headers['X-RateLimit-Reset'])
        if 'Retry-After' in headers:
            retry_after = headers['Retry-After']
            if retry_after.isdigit():
                rate_limit_info['reset_time'] = time.time() + int(retry_after)

        if rate_limit_info:
            self.rate_limits[key] = rate_limit_info

        return response_info

    async def on_error(self, error_info: ErrorInfo) -> bool:
        if error_info.response_info and error_info.response_info.status_code == 429:
            key = error_info.request_info.key
            print(f"⚠️  Rate limit hit for key {key[:8]}...")

            if 'Retry-After' in error_info.response_info.headers:
                retry_after = int(error_info.response_info.headers['Retry-After'])
                self.rate_limits[key] = {'reset_time': time.time() + retry_after}
            else:
                self.rate_limits[key] = {'reset_time': time.time() + 60}

            return True
        return False
