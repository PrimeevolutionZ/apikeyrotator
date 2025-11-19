"""
Middleware for logging
"""
import logging
from typing import Optional
from .models import RequestInfo, ResponseInfo, ErrorInfo


class LoggingMiddleware:
    """
    Middleware for logging requests and responses.
    """

    def __init__(
        self,
        verbose: bool = True,
        logger: Optional[logging.Logger] = None,
        log_level: int = logging.INFO,
        log_response_time: bool = True,
        max_key_chars: int = 4
    ):
        """
        Args:
            verbose: Detailed logging (including keys and headers)
            logger: Logger for output. If None, a new one is created
            log_level: Log level (DEBUG, INFO, WARNING, etc.)
            log_response_time: Whether to log request duration
            max_key_chars: Max characters of key to log (for safety)
        """
        self.verbose = verbose
        self.log_response_time = log_response_time
        self.max_key_chars = max(0, min(8, max_key_chars))  # Max 8 characters

        # FIXED: Use real logger
        if logger:
            self.logger = logger
        else:
            self.logger = logging.getLogger(__name__)
            if not self.logger.handlers:
                handler = logging.StreamHandler()
                formatter = logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                )
                handler.setFormatter(formatter)
                self.logger.addHandler(handler)

        self.logger.setLevel(log_level)

        self.logger.info(
            f"LoggingMiddleware initialized: verbose={verbose}, "
            f"log_response_time={log_response_time}"
        )

    def _mask_key(self, key: str) -> str:
        """
        Args:
            key: Full API key

        Returns:
            str: Masked key (e.g. "sk-ab****")
        """
        if len(key) <= self.max_key_chars:
            return key[:self.max_key_chars] + "****"
        return key[:self.max_key_chars] + "****"

    def _format_headers(self, headers: dict) -> str:
        """
        Formats headers for logging, hiding sensitive data.

        Args:
            headers: Headers dict

        Returns:
            str: Safe headers string
        """
        safe_headers = {}
        sensitive_keys = ['authorization', 'x-api-key', 'cookie', 'set-cookie']

        for key, value in headers.items():
            if key.lower() in sensitive_keys:
                safe_headers[key] = "[REDACTED]"
            else:
                safe_headers[key] = value

        return str(safe_headers)

    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        """
        Logs information before sending request.
        """
        if self.verbose:
            masked_key = self._mask_key(request_info.key)
            headers_str = self._format_headers(request_info.headers)

            self.logger.info(
                f"📤 {request_info.method} {request_info.url} "
                f"(key: {masked_key}, attempt: {request_info.attempt + 1})"
            )

            self.logger.debug(f"Headers: {headers_str}")

            if request_info.kwargs.get('json'):
                self.logger.debug(f"JSON body: {request_info.kwargs['json']}")
        else:
            self.logger.info(f"📤 {request_info.method} {request_info.url}")

        return request_info

    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        """
        Logs information after receiving response.
        """
        status = response_info.status_code
        url = response_info.request_info.url

        # Determine log level by status code
        if 200 <= status < 300:
            log_level = logging.INFO
            emoji = "📥 ✅"
        elif 400 <= status < 500:
            log_level = logging.WARNING
            emoji = "📥 ⚠️"
        else:
            log_level = logging.ERROR
            emoji = "📥 ❌"

        message = f"{emoji} {status} from {url}"

        if self.verbose:
            masked_key = self._mask_key(response_info.request_info.key)
            message += f" (key: {masked_key})"

        # Log response time if available
        if self.log_response_time and hasattr(response_info, 'response_time'):
            message += f" ({response_info.response_time:.3f}s)"

        self.logger.log(log_level, message)

        # Detailed response headers logging
        if self.verbose and self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(
                f"Response headers: {self._format_headers(response_info.headers)}"
            )

        return response_info

    async def on_error(self, error_info: ErrorInfo) -> bool:
        """
        Logs errors.
        """
        exception = error_info.exception
        url = error_info.request_info.url
        masked_key = self._mask_key(error_info.request_info.key)

        self.logger.error(
            f"❌ Error for {url}: {type(exception).__name__}: {str(exception)}"
        )

        if self.verbose:
            self.logger.error(f"   Key: {masked_key}, Attempt: {error_info.request_info.attempt + 1}")

            # Log traceback only in DEBUG mode
            if self.logger.isEnabledFor(logging.DEBUG):
                import traceback
                self.logger.debug(f"Traceback:\n{''.join(traceback.format_tb(exception.__traceback__))}")

        return False  # Do not handle error, only log