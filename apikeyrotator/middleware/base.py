"""Base protocol for middleware"""

from typing import Protocol
from .models import RequestInfo, ResponseInfo, ErrorInfo


class RotatorMiddleware(Protocol):
    """
    Protocol for rotator middleware.

    Middleware allows intercepting and modifying requests,
    responses, and handling errors.
    """

    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        """Called before sending the request"""
        return request_info

    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        """Called after a successful response"""
        return response_info

    async def on_error(self, error_info: ErrorInfo) -> bool:
        """
        Called when an error occurs.

        Returns:
            bool: True if the error was handled, False to propagate
        """
        return False