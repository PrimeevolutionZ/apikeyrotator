from typing import Any


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
        possibly_processed: True if a non-idempotent request (POST/PATCH) was retried
            after a failure where the server may already have executed it (only happens
            with an Idempotency-Key or retry_non_idempotent=True). Don't send it anywhere
            else (FallbackRouter doesn't) - check its outcome first.
    """

    possibly_processed: bool = False

    def __init__(
            self,
            message: str = "",
            last_response: Any | None = None,
            last_exception: BaseException | None = None,
    ):
        super().__init__(message)
        self.last_response = last_response
        self.last_exception = last_exception


class AuthenticationError(AllKeysExhaustedError):
    """
    Every key was rejected (401/403) and no request has succeeded yet.

    This almost always means the API expects a different auth header, not that
    all keys are invalid - so the keys are kept (and not reported to a shared
    state backend). Fix the header with ``auth=`` or ``header_callback=``.

    Attributes:
        statuses: Rejection status per masked key, e.g. ``{"sk-1****": 401}``.
        auth_header: The auth header that was sent, with the key masked.
    """

    def __init__(self, message: str, statuses: dict[str, int] | None = None,
                 auth_header: str | None = None, **kwargs):
        super().__init__(message, **kwargs)
        self.statuses = statuses or {}
        self.auth_header = auth_header


class AllProvidersExhaustedError(APIKeyError):
    """All providers (and their keys) are exhausted"""
    pass


class HTTPStatusError(APIKeyError):
    """
    Error-status HTTP response. Passed to middleware ``on_error`` hooks
    when the server answers with a retryable or permanent error status.
    """

    def __init__(self, status_code: int, message: str = "", response: Any | None = None):
        super().__init__(message or f"HTTP {status_code}")
        self.status_code = status_code
        #: The response (set by UnifiedResponse.raise_for_status())
        self.response = response


class DeadlineExceededError(AllKeysExhaustedError, TimeoutError):
    """
    The request's total time budget (``total_timeout``) ran out, including
    all retries and waits. Also a ``TimeoutError``.

    FallbackRouter does not fall back to other providers on this error - the
    caller's deadline is already spent.
    """


class CircuitOpenError(AllKeysExhaustedError):
    """
    The circuit breaker for the target host is open: the host failed repeatedly,
    so requests fail fast without touching the network until ``retry_after``
    seconds have passed. FallbackRouter treats it like an exhausted provider.

    Attributes:
        host: Host whose circuit is open.
        retry_after: Seconds until a probe request will be allowed.
    """

    def __init__(self, host: str, retry_after: float, **kwargs):
        super().__init__(
            f"Circuit breaker open for {host}; retry in {retry_after:.1f}s", **kwargs
        )
        self.host = host
        self.retry_after = retry_after
