from enum import Enum
from typing import Optional
import requests


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


class ErrorClassifier:
    """
    HTTP request error classifier.
    Determines the error type to decide whether a retry is needed
    and whether to switch API keys.
    """

    def __init__(self, custom_retryable_codes: Optional[list] = None):
        """
        Args:
            custom_retryable_codes: Additional status codes considered temporary
        """
        self.custom_retryable_codes = set(custom_retryable_codes or [])

    def classify_error(
            self,
            response: Optional[requests.Response] = None,
            exception: Optional[Exception] = None
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
            if isinstance(exception, (
                    requests.exceptions.ConnectionError,
                    requests.exceptions.ConnectTimeout,
                    requests.exceptions.ReadTimeout,
                    requests.exceptions.Timeout
            )):
                return ErrorType.NETWORK

            # SSL errors - usually temporary (may be proxy certificate issues)
            if isinstance(exception, requests.exceptions.SSLError):
                return ErrorType.TEMPORARY

            # Other requests exceptions
            if isinstance(exception, requests.exceptions.RequestException):
                return ErrorType.NETWORK

            return ErrorType.UNKNOWN

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

    def is_retryable(
            self,
            response: Optional[requests.Response] = None,
            exception: Optional[Exception] = None
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
            response: Optional[requests.Response] = None,
            exception: Optional[Exception] = None
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
            response: Optional[requests.Response] = None,
            exception: Optional[Exception] = None
    ) -> bool:
        """
        Determines whether to remove the API key from rotation.

        Args:
            response: HTTP response from server (optional)
            exception: Exception raised during request (optional)

        Returns:
            bool: True if key should be removed, False otherwise
        """
        error_type = self.classify_error(response, exception)
        # Remove only on explicitly permanent errors (401, 403)
        if response and response.status_code in [401, 403]:
            return True
        return error_type == ErrorType.PERMANENT and response and response.status_code in [401, 403]

    def get_retry_delay(
            self,
            response: Optional[requests.Response] = None,
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
        if not response:
            return default_delay

        # Check Retry-After header
        retry_after = response.headers.get('Retry-After')
        if retry_after:
            try:
                # May be number of seconds
                if retry_after.isdigit():
                    return float(retry_after)
                # Or HTTP date
                from email.utils import parsedate_to_datetime
                import time
                target_time = parsedate_to_datetime(retry_after).timestamp()
                delay = max(0, target_time - time.time())
                return delay
            except (ValueError, TypeError):
                pass

        # For rate limit, usually wait longer
        if response.status_code == 429:
            return default_delay * 5

        # For server errors - standard delay
        if 500 <= response.status_code < 600:
            return default_delay

        return default_delay