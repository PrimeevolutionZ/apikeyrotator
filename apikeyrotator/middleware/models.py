"""Data models for middleware"""

from typing import Any, Dict, Optional


class RequestInfo:
    """Information about an HTTP request"""

    def __init__(
            self,
            method: str,
            url: str,
            headers: Dict[str, str],
            cookies: Dict[str, str],
            key: str,
            attempt: int,
            kwargs: Dict[str, Any]
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

    def __init__(
            self,
            status_code: int,
            headers: Dict[str, str],
            content: Any,
            request_info: RequestInfo
    ):
        self.status_code = status_code
        self.headers = headers
        self.content = content
        self.request_info = request_info


class ErrorInfo:
    """Information about an error"""

    def __init__(
            self,
            exception: Exception,
            request_info: RequestInfo,
            response_info: Optional[ResponseInfo] = None
    ):
        self.exception = exception
        self.request_info = request_info
        self.response_info = response_info