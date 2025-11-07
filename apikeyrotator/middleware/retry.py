"""Middleware для управления retry логикой"""

import asyncio
from typing import Dict
from .models import RequestInfo, ResponseInfo, ErrorInfo


class RetryMiddleware:
    """Middleware для управления retry"""

    def __init__(self, max_retries: int = 3, backoff_factor: float = 2.0):
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.retry_counts: Dict[str, int] = {}

    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        return request_info

    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        url = response_info.request_info.url
        if url in self.retry_counts:
            del self.retry_counts[url]
        return response_info

    async def on_error(self, error_info: ErrorInfo) -> bool:
        url = error_info.request_info.url
        retry_count = self.retry_counts.get(url, 0)

        if retry_count < self.max_retries:
            self.retry_counts[url] = retry_count + 1
            wait_time = self.backoff_factor ** retry_count
            print(f"🔄 Retry {retry_count + 1}/{self.max_retries} after {wait_time:.1f}s")
            await asyncio.sleep(wait_time)
            return True

        del self.retry_counts[url]
        return False