import time
from collections.abc import Mapping
from email.utils import parsedate_to_datetime
from enum import Enum
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:  # requests is imported lazily - only needed to classify its exceptions
    import requests

# Values below this are "seconds until reset", larger values are UNIX timestamps
_EPOCH_THRESHOLD = 1_000_000_000


# Header containers that already do case-insensitive lookups (requests, aiohttp/multidict, httpx)
_CASE_INSENSITIVE_HEADERS = frozenset({
    "CaseInsensitiveDict", "CIMultiDict", "CIMultiDictProxy", "Headers",
})


def get_header(headers: Mapping[str, Any] | None, name: str) -> str | None:
    """
    Case-insensitive header lookup that works for plain dicts as well as
    requests/aiohttp/httpx case-insensitive mappings.
    """
    if not headers:
        return None
    try:
        value = headers.get(name)
    except AttributeError:
        return None
    if value is not None or type(headers).__name__ in _CASE_INSENSITIVE_HEADERS:
        return None if value is None else str(value)
    name_lower = name.lower()
    for k, v in headers.items():
        if isinstance(k, str) and k.lower() == name_lower:
            return None if v is None else str(v)
    return None


def parse_retry_after(headers: Mapping[str, Any] | None) -> float | None:
    """
    Parses the ``Retry-After`` header.

    Supports both forms defined by RFC 9110: delay in seconds (integer or
    fractional) and an HTTP-date.

    Returns:
        Delay in seconds (>= 0) or None if the header is missing/invalid.
    """
    value = get_header(headers, 'Retry-After')
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        target = parsedate_to_datetime(value).timestamp()
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    return max(0.0, target - time.time())


class ErrorType(Enum):
    """
    Types of errors for classifying HTTP requests.

    Attributes:
        RATE_LIMIT: Request limit exceeded (429)
        TEMPORARY: Temporary server error (5xx, 408, some network errors)
        PERMANENT: Permanent error (401, 403, 404, 410)
        NETWORK: Network or connection issues
        UNKNOWN: Unknown error type
    """
    RATE_LIMIT = "rate_limit"
    TEMPORARY = "temporary"
    PERMANENT = "permanent"
    NETWORK = "network"
    UNKNOWN = "unknown"


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        # Some APIs send lists like "100, 100;w=60" - take the first value
        return float(str(value).split(',')[0].split(';')[0].strip())
    except (ValueError, TypeError):
        return None


def to_reset_timestamp(value: float, now: float | None = None) -> float:
    """Normalizes a rate-limit reset value (delta seconds or UNIX timestamp) to a UNIX timestamp."""
    if now is None:
        now = time.time()
    if value < _EPOCH_THRESHOLD:
        return now + max(0.0, value)
    return value


_RATE_LIMIT_FIELDS = {
    # lower-cased header -> (field index, priority); X- variant wins over IETF draft
    'x-ratelimit-limit': (0, 0), 'ratelimit-limit': (0, 1),
    'x-ratelimit-remaining': (1, 0), 'ratelimit-remaining': (1, 1),
    'x-ratelimit-reset': (2, 0), 'ratelimit-reset': (2, 1),
}
_CI_NAMES = (
    ('X-RateLimit-Limit', 'RateLimit-Limit'),
    ('X-RateLimit-Remaining', 'RateLimit-Remaining'),
    ('X-RateLimit-Reset', 'RateLimit-Reset'),
)


def rate_limit_header_values(headers: Mapping[str, Any] | None) -> tuple[Any, Any, Any]:
    """
    Raw (limit, remaining, reset) header values - ``X-RateLimit-*`` preferred over
    the IETF ``RateLimit-*`` names. Hot path: case-insensitive containers get direct
    lookups, plain dicts are scanned exactly once.
    """
    if not headers:
        return None, None, None
    if type(headers).__name__ in _CASE_INSENSITIVE_HEADERS:
        get = headers.get
        out = []
        for primary, secondary in _CI_NAMES:
            value = get(primary)
            out.append(get(secondary) if value is None else value)
        return out[0], out[1], out[2]
    values: list[Any] = [None, None, None]
    prios = [2, 2, 2]
    try:
        items = headers.items()
    except AttributeError:
        return None, None, None
    fields = _RATE_LIMIT_FIELDS
    for k, v in items:
        if not isinstance(k, str) or not 15 <= len(k) <= 21:
            continue  # cheap filter: all names are 15..21 chars long
        hit = fields.get(k.lower())
        if hit is not None:
            idx, prio = hit
            if prio < prios[idx]:
                values[idx], prios[idx] = v, prio
    return values[0], values[1], values[2]


def parse_rate_limit_headers(headers: Mapping[str, Any] | None) -> tuple[float | None, float | None]:
    """
    Reads ``X-RateLimit-Remaining``/``-Reset`` (or the IETF ``RateLimit-*`` variant).

    Returns:
        (remaining, reset_timestamp) - each None if the header is missing/invalid.
    """
    _, remaining_raw, reset_raw = rate_limit_header_values(headers)
    if remaining_raw is None:
        return None, None
    remaining = _parse_number(remaining_raw)
    reset = _parse_number(reset_raw)
    return remaining, (to_reset_timestamp(reset) if reset is not None else None)


class ErrorClassifier:
    """
    HTTP request error classifier.
    Determines the error type to decide whether a retry is needed
    and whether to switch API keys.
    """

    def __init__(self, custom_retryable_codes: list | None = None):
        """
        Args:
            custom_retryable_codes: Additional status codes considered temporary
        """
        self.custom_retryable_codes = set(custom_retryable_codes or [])

    def classify_error(
            self,
            response: "requests.Response | None" = None,
            exception: Exception | None = None
    ) -> ErrorType:
        """
        Classifies errors to decide whether to retry.

         More precise logic for 4xx codes:
        - 408 Request Timeout - TEMPORARY (can retry)
        - 409 Conflict - TEMPORARY (may resolve)
        - 429 Too Many Requests - RATE_LIMIT
        - 511 Network Authentication Required - TEMPORARY (FIXED #8)
        - 401, 403 - PERMANENT (key issue)
        - 404, 410 - PERMANENT (resource does not exist)
        - Other 4xx - PERMANENT

        Classification logic:
        - RATE_LIMIT (429): need to switch key
        - TEMPORARY (5xx, 408, 409, 503, 511): can retry with the same key
        - PERMANENT (401, 403, 404, 410, other 4xx): key is invalid or request is incorrect
        - NETWORK: network/proxy issues, can retry
        - UNKNOWN: unknown error

        Args:
            response: HTTP response from server (optional)
            exception: Exception raised during request (optional)

        Returns:
            ErrorType: Classified error type

        Examples:
            >>> classifier = ErrorClassifier()
            >>> # Classification by response
            >>> error_type = classifier.classify_error(response=response_obj)
            >>> # Classification by exception
            >>> error_type = classifier.classify_error(exception=connection_error)
        """
        # Classify exceptions
        if exception:
            return self._classify_exception(exception)

        # If no response, return UNKNOWN
        if response is None:
            return ErrorType.UNKNOWN

        status_code = response.status_code

        # User-defined retry codes
        if status_code in self.custom_retryable_codes:
            return ErrorType.TEMPORARY

        # Classification by status code
        if status_code == 429:
            # Too Many Requests - Rate Limit
            return ErrorType.RATE_LIMIT

        # FIXED: More detailed 4xx classification
        elif status_code == 408:
            # Request Timeout - temporary error, can retry
            return ErrorType.TEMPORARY

        elif status_code == 409:
            # Conflict - may resolve on retry (e.g., concurrent updates)
            return ErrorType.TEMPORARY

        elif status_code == 425:
            # Too Early - server not ready to process request, can retry
            return ErrorType.TEMPORARY

        elif status_code == 511:
            # Can be temporary if network auth becomes available
            # (e.g., captive portal, NTLM proxy)
            return ErrorType.TEMPORARY

        elif status_code in [401, 403]:
            # Unauthorized, Forbidden - API key issue
            return ErrorType.PERMANENT

        elif status_code in [404, 410]:
            # Not Found, Gone - resource does not exist (invalid endpoint)
            return ErrorType.PERMANENT

        elif status_code in [400, 405, 406, 411, 412, 413, 414, 415, 416, 417, 422, 428, 431]:
            # Client errors related to malformed requests
            # 400 Bad Request
            # 405 Method Not Allowed
            # 406 Not Acceptable
            # 411 Length Required
            # 412 Precondition Failed
            # 413 Payload Too Large
            # 414 URI Too Long
            # 415 Unsupported Media Type
            # 416 Range Not Satisfiable
            # 417 Expectation Failed
            # 422 Unprocessable Entity
            # 428 Precondition Required
            # 431 Request Header Fields Too Large
            return ErrorType.PERMANENT

        elif 400 <= status_code < 500:
            # Other 4xx - considered permanent (bad request)
            return ErrorType.PERMANENT

        # Server errors
        elif status_code in [500, 502, 503, 504]:
            # Internal Server Error, Bad Gateway, Service Unavailable, Gateway Timeout
            # Usually temporary issues
            return ErrorType.TEMPORARY

        elif status_code == 507:
            # Insufficient Storage - may be temporary
            return ErrorType.TEMPORARY

        elif 500 <= status_code < 600:
            # Other 5xx - considered temporary
            return ErrorType.TEMPORARY

        # 2xx, 3xx and other codes - not errors
        return ErrorType.UNKNOWN

    @staticmethod
    def _classify_exception(exception: BaseException) -> "ErrorType":
        module = type(exception).__module__ or ""
        if module.startswith("requests"):
            import requests

            if isinstance(exception, (
                    requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout,
            )):
                return ErrorType.NETWORK
            # SSL errors - usually temporary (may be proxy certificate issues)
            if isinstance(exception, requests.exceptions.SSLError):
                return ErrorType.TEMPORARY
            if isinstance(exception, requests.exceptions.RequestException):
                return ErrorType.NETWORK
            return ErrorType.UNKNOWN
        if module.startswith(("aiohttp", "httpx", "httpcore")):
            return ErrorType.NETWORK
        if isinstance(exception, (TimeoutError, ConnectionError)):
            return ErrorType.NETWORK
        return ErrorType.UNKNOWN

    def is_retryable(
            self,
            response: "requests.Response | None" = None,
            exception: Exception | None = None
    ) -> bool:
        """
        Determines whether the request can be retried.

        Args:
            response: HTTP response from server (optional)
            exception: Exception raised during request (optional)

        Returns:
            bool: True if request can be retried, False otherwise
        """
        error_type = self.classify_error(response, exception)
        return error_type in [ErrorType.RATE_LIMIT, ErrorType.TEMPORARY, ErrorType.NETWORK]

    def should_switch_key(
            self,
            response: "requests.Response | None" = None,
            exception: Exception | None = None
    ) -> bool:
        """
        Determines whether to switch the API key.

        Args:
            response: HTTP response from server (optional)
            exception: Exception raised during request (optional)

        Returns:
            bool: True if key should be switched, False otherwise
        """
        error_type = self.classify_error(response, exception)
        # Switch key on rate limit or permanent errors
        return error_type in [ErrorType.RATE_LIMIT, ErrorType.PERMANENT]

    def should_remove_key(
            self,
            response: "requests.Response | None" = None,
            exception: Exception | None = None
    ) -> bool:
        """
        Determines whether to remove the API key from rotation.

        Args:
            response: HTTP response from server (optional)
            exception: Exception raised during request (optional)

        Returns:
            bool: True if key should be removed, False otherwise
        """
        # NOTE: `response is not None` is required here - requests.Response
        # defines __bool__ as `response.ok`, so an error response is falsy.
        if response is None:
            return False
        # Remove only on explicitly permanent auth errors (401, 403)
        return response.status_code in (401, 403)

    def get_retry_delay(
            self,
            response: "requests.Response | None" = None,
            default_delay: float = 1.0
    ) -> float:
        """
        Determines optimal retry delay based on response.

        Args:
            response: HTTP response from server
            default_delay: Default delay

        Returns:
            float: Recommended delay in seconds
        """
        if response is None:
            return default_delay

        # Check Retry-After header (seconds or HTTP-date)
        retry_after = parse_retry_after(getattr(response, 'headers', None))
        if retry_after is not None:
            return retry_after

        # For rate limit, usually wait longer
        if response.status_code == 429:
            return default_delay * 5

        # For server errors - standard delay
        if 500 <= response.status_code < 600:
            return default_delay

        return default_delay