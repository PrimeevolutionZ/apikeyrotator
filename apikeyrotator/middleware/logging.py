"""Middleware для логирования"""

from .models import RequestInfo, ResponseInfo, ErrorInfo


class LoggingMiddleware:
    """Middleware для логирования запросов и ответов"""

    def __init__(self, verbose: bool = True):
        self.verbose = verbose

    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        if self.verbose:
            print(f"📤 {request_info.method} {request_info.url} (key: {request_info.key[:8]}...)")
        else:
            print(f"📤 {request_info.method} {request_info.url}")
        return request_info

    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        if self.verbose:
            print(f"📥 {response_info.status_code} from {response_info.request_info.url}")
        return response_info

    async def on_error(self, error_info: ErrorInfo) -> bool:
        print(f"❌ Error: {error_info.exception} for {error_info.request_info.url}")
        return False