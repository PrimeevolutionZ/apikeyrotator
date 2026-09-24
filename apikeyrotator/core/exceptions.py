from typing import Any, Optional


class APIKeyError(Exception):
    """Base exception for API key errors"""
    pass


class NoAPIKeysError(APIKeyError):
    """No API keys found"""
    pass


class AllKeysExhaustedError(APIKeyError):
    """
    All keys are exhausted.

    Attributes:
        last_response: The last HTTP response received before giving up (if any).
        last_exception: The last network exception raised before giving up (if any).
    """

    def __init__(
            self,
            message: str = "",
            last_response: Optional[Any] = None,
            last_exception: Optional[BaseException] = None,
    ):
        super().__init__(message)
        self.last_response = last_response
        self.last_exception = last_exception


class AllProvidersExhaustedError(APIKeyError):
    """All providers (and their keys) are exhausted"""
    pass


class HTTPStatusError(APIKeyError):
    """
    Error-status HTTP response. Passed to middleware ``on_error`` hooks
    when the server answers with a retryable or permanent error status.
    """

    def __init__(self, status_code: int, message: str = ""):
        super().__init__(message or f"HTTP {status_code}")
        self.status_code = status_code
