"""
Middleware package - middleware system for intercepting requests/responses
The purpose of the module is to provide an extensible and modular architecture for adding cross-cutting logic
(such as logging, caching, retries, and rate-limiting) to HTTP requests executed by the rotator.
"""

from .base import RotatorMiddleware
from .models import RequestInfo, ResponseInfo, ErrorInfo
from .logging import LoggingMiddleware
from .caching import CachingMiddleware
from .rate_limit import RateLimitMiddleware
from .retry import RetryMiddleware

__all__ = [
    "RotatorMiddleware",
    "RequestInfo",
    "ResponseInfo",
    "ErrorInfo",
    "LoggingMiddleware",
    "CachingMiddleware",
    "RateLimitMiddleware",
    "RetryMiddleware",
]