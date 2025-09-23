from typing import Any, Dict, Optional, Protocol, Tuple, Union

class RequestInfo:
    def __init__(self, method: str, url: str, headers: Dict[str, str], cookies: Dict[str, str], key: str, attempt: int, kwargs: Dict[str, Any]):
        self.method = method
        self.url = url
        self.headers = headers
        self.cookies = cookies
        self.key = key
        self.attempt = attempt
        self.kwargs = kwargs

class ResponseInfo:
    def __init__(self, status_code: int, headers: Dict[str, str], content: Any, request_info: RequestInfo):
        self.status_code = status_code
        self.headers = headers
        self.content = content
        self.request_info = request_info

class ErrorInfo:
    def __init__(self, exception: Exception, request_info: RequestInfo, response_info: Optional[ResponseInfo] = None):
        self.exception = exception
        self.request_info = request_info
        self.response_info = response_info

class RotatorMiddleware(Protocol):
    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        """Called before a request is made. Can modify request_info."""
        return request_info

    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        """Called after a request is successfully completed. Can modify response_info."""
        return response_info

    async def on_error(self, error_info: ErrorInfo) -> bool:
        """Called when an error occurs during a request. Return True if the error is handled and should not be re-raised."""
        return False

# Example Middleware
class RateLimitMiddleware:
    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        # Implement rate limit checks here
        return request_info

    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        # Update rate limit stats based on response headers
        return response_info

    async def on_error(self, error_info: ErrorInfo) -> bool:
        # Handle rate limit errors, e.g., by pausing or switching keys
        if error_info.response_info and error_info.response_info.status_code == 429:
            print(f"Rate limit hit for key {error_info.request_info.key}")
            # Logic to handle rate limit, e.g., mark key as unhealthy, wait, etc.
            return True # Indicate that the error was handled
        return False

class CachingMiddleware:
    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        # Check cache for response
        return request_info

    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        # Cache successful responses
        return response_info

    async def on_error(self, error_info: ErrorInfo) -> bool:
        return False


