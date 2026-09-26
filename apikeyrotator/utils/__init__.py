"""Utilities: error classification, circuit breaker, retry helpers."""

from typing import Any

from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from .error_classifier import (
    ErrorClassifier,
    ErrorType,
    get_header,
    parse_rate_limit_headers,
    parse_retry_after,
)
from .retry import async_retry_with_backoff, retry_with_backoff


__all__ = [
    "ErrorClassifier",
    "ErrorType",
    "get_header",
    "parse_retry_after",
    "parse_rate_limit_headers",
    "retry_with_backoff",
    "async_retry_with_backoff",
    "CircuitBreaker",
    "CircuitBreakerConfig",
]


def __getattr__(name: str) -> Any:
    from . import _deprecated

    if name in _deprecated.REPLACEMENTS:
        return _deprecated.warn(name, __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
