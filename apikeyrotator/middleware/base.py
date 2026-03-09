from abc import ABC
from typing import Dict, Optional, Any
import logging


class RotatorMiddleware(ABC):
    """
    Abstract base class for middleware.
    Supports both synchronous and asynchronous methods.
    """

    # --- Async methods (for AsyncAPIKeyRotator) ---

    async def before_request(self, request_info: 'RequestInfo') -> 'RequestInfo':
        """Async hook before request"""
        return self.before_request_sync(request_info)

    async def after_request(self, response_info: 'ResponseInfo') -> 'ResponseInfo':
        """Async hook after response"""
        return self.after_request_sync(response_info)

    async def on_error(self, error_info: 'ErrorInfo') -> bool:
        """Async hook on error"""
        return self.on_error_sync(error_info)

    # --- Sync methods (for APIKeyRotator) ---

    def before_request_sync(self, request_info: 'RequestInfo') -> 'RequestInfo':
        """Sync hook before request"""
        return request_info

    def after_request_sync(self, response_info: 'ResponseInfo') -> 'ResponseInfo':
        """Sync hook after response"""
        return response_info

    def on_error_sync(self, error_info: 'ErrorInfo') -> bool:
        """Sync hook on error"""
        return False
