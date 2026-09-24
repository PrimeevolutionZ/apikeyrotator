"""Data models for middleware"""

from typing import Any


class RequestInfo:
    """Information about an HTTP request"""

    __slots__ = ("method", "url", "headers", "cookies", "key", "attempt", "kwargs")

    def __init__(
            self,
            method: str,
            url: str,
            headers: dict[str, str],
            cookies: dict[str, str],
            key: str,
            attempt: int,
            kwargs: dict[str, Any]
    ):
        self.method = method
        self.url = url
        self.headers = headers
        self.cookies = cookies
        self.key = key
        self.attempt = attempt
        self.kwargs = kwargs


class ResponseInfo:
    """Information about an HTTP response"""

    __slots__ = ("status_code", "headers", "content", "request_info", "response_time")

    def __init__(
            self,
            status_code: int,
            headers: dict[str, str],
            content: Any,
            request_info: RequestInfo,
            response_time: float | None = None
    ):
        self.status_code = status_code
        self.headers = headers
        self.content = content
        self.request_info = request_info
        self.response_time = response_time


class ErrorInfo:
    """Information about an error"""

    __slots__ = ("exception", "request_info", "response_info")

    def __init__(
            self,
            exception: Exception,
            request_info: RequestInfo,
            response_info: ResponseInfo | None = None
    ):
        self.exception = exception
        self.request_info = request_info
        self.response_info = response_info