"""
Middleware for logging
"""
import logging
import time
from typing import Optional
from .base import RotatorMiddleware
from .models import RequestInfo, ResponseInfo, ErrorInfo


class LoggingMiddleware(RotatorMiddleware):
    """
    Middleware for logging requests and responses.
    Supports both Sync and Async execution.
    """

    def __init__(
        self,
        verbose: bool = True,
        logger: Optional[logging.Logger] = None,
        log_level: int = logging.INFO,
        log_response_time: bool = True,
        max_key_chars: int = 4,
        max_logs_per_second: int = 1000
    ):
        self.verbose = verbose
        self.log_response_time = log_response_time
        self.max_key_chars = max(0, min(8, max_key_chars))
        self.max_logs_per_second = max_logs_per_second

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

        self._last_log_reset = time.time()
        self._log_count = 0
        self._dropped_logs = 0

    def _should_log(self) -> bool:
        current_time = time.time()
        if current_time - self._last_log_reset >= 1.0:
            if self._dropped_logs > 0:
                self.logger.warning(
                    f"⚠️ Dropped {self._dropped_logs} log messages due to rate limiting"
                )
            self._last_log_reset = current_time
            self._log_count = 0
            self._dropped_logs = 0

        if self._log_count >= self.max_logs_per_second:
            self._dropped_logs += 1
            return False

        self._log_count += 1
        return True

    def _mask_key(self, key: str) -> str:
        if len(key) <= self.max_key_chars:
            return key[:self.max_key_chars] + "****"
        return key[:self.max_key_chars] + "****"

    def _format_headers(self, headers: dict) -> str:
        safe_headers = {}
        sensitive_keys = ['authorization', 'x-api-key', 'cookie', 'set-cookie']
        for key, value in headers.items():
            if key.lower() in sensitive_keys:
                safe_headers[key] = "[REDACTED]"
            else:
                safe_headers[key] = value
        return str(safe_headers)

    # --- Implementation (Common Logic) ---

    def _log_request(self, request_info: RequestInfo):
        if not self._should_log():
            return

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

    def _log_response(self, response_info: ResponseInfo):
        if not self._should_log():
            return

        status = response_info.status_code
        url = response_info.request_info.url

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

        if self.log_response_time and hasattr(response_info, 'response_time'):
            message += f" ({response_info.response_time:.3f}s)"

        self.logger.log(log_level, message)

        if self.verbose and self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(
                f"Response headers: {self._format_headers(response_info.headers)}"
            )

    def _log_error(self, error_info: ErrorInfo):
        if not self._should_log():
            return

        exception = error_info.exception
        url = error_info.request_info.url
        masked_key = self._mask_key(error_info.request_info.key)

        self.logger.error(
            f"❌ Error for {url}: {type(exception).__name__}: {str(exception)}"
        )

        if self.verbose:
            self.logger.error(f"   Key: {masked_key}, Attempt: {error_info.request_info.attempt + 1}")
            if self.logger.isEnabledFor(logging.DEBUG):
                import traceback
                self.logger.debug(f"Traceback:\n{''.join(traceback.format_tb(exception.__traceback__))}")

    # --- Sync Hooks ---

    def before_request_sync(self, request_info: RequestInfo) -> RequestInfo:
        self._log_request(request_info)
        return request_info

    def after_request_sync(self, response_info: ResponseInfo) -> ResponseInfo:
        self._log_response(response_info)
        return response_info

    def on_error_sync(self, error_info: ErrorInfo) -> bool:
        self._log_error(error_info)
        return False

    # --- Async Hooks (Delegate to Sync logic as logging is blocking anyway or fast enough) ---

    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        return self.before_request_sync(request_info)

    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        return self.after_request_sync(response_info)

    async def on_error(self, error_info: ErrorInfo) -> bool:
        return self.on_error_sync(error_info)