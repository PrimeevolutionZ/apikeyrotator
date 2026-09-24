import time
import json
import inspect
import requests
import requests.adapters
import asyncio
import aiohttp
import logging
import random
import threading
from enum import Enum
from http import HTTPStatus
from typing import Any, List, Optional, Dict, Union, Callable, Tuple, Awaitable
from urllib.parse import urlsplit, urlunsplit

from .key_parser import parse_keys
from .exceptions import AllKeysExhaustedError, HTTPStatusError
from apikeyrotator.strategies import (
    RotationStrategy,
    create_rotation_strategy,
    BaseRotationStrategy,
    KeyMetrics
)
from apikeyrotator.metrics import RotatorMetrics
from apikeyrotator.middleware import RotatorMiddleware, RequestInfo, ResponseInfo, ErrorInfo
from apikeyrotator.utils import ErrorClassifier, ErrorType, parse_retry_after
from .config_loader import ConfigLoader
from apikeyrotator.providers import SecretProvider

try:
    from dotenv import load_dotenv

    _DOTENV_INSTALLED = True
except ImportError:
    _DOTENV_INSTALLED = False

# ============================================================================
# CONSTANTS
# ============================================================================

API_KEY_PATTERNS = {
    'bearer': ('sk-', 'pk-'),
    'api_key': 32,
}

DEFAULT_AUTH_HEADERS = {
    'bearer': 'Authorization',
    'api_key': 'X-API-Key',
}

KEY_LOG_LENGTH = 4
KEY_LOG_SUFFIX = '****'

DEFAULT_MAX_DELAY = 60.0
DEFAULT_POOL_SIZE = 100


def _mask_key(key: str) -> str:
    return f"{key[:KEY_LOG_LENGTH]}{KEY_LOG_SUFFIX}"


class _ResponseCodeWrapper:
    """Wrapper for status code to simulate response object behavior for classifier"""
    __slots__ = ('status_code', 'headers')

    def __init__(self, status_code: int, headers: Optional[Dict[str, str]] = None):
        self.status_code = status_code
        self.headers = headers or {}


class _Action(Enum):
    """What the request loop should do after a response was classified."""
    RETURN = "return"  # hand the response to the caller
    RETRY = "retry"  # retry (consumes one attempt)
    SWITCH = "switch"  # key was removed, retry with another key (no attempt consumed)


class _CachedAsyncResponse:
    """Minimal aiohttp.ClientResponse-like object returned for middleware short-circuits (e.g. cache hits)."""

    def __init__(self, status: int, headers: Optional[Dict[str, str]], content: Any, url: str = ""):
        self.status = status
        self.headers = dict(headers or {})
        self.url = url
        if content is None:
            content = b''
        self._content = content if isinstance(content, bytes) else str(content).encode('utf-8')

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 400

    @property
    def reason(self) -> str:
        try:
            return HTTPStatus(self.status).phrase
        except ValueError:
            return ""

    async def read(self) -> bytes:
        return self._content

    async def text(self, encoding: str = 'utf-8') -> str:
        return self._content.decode(encoding)

    async def json(self, **kwargs) -> Any:
        return json.loads(self._content)

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise HTTPStatusError(self.status)

    def release(self) -> None:
        pass

    def close(self) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


def _build_sync_response(info: ResponseInfo, url: str) -> requests.Response:
    """Builds a requests.Response from a middleware-provided ResponseInfo (e.g. cache hit)."""
    response = requests.Response()
    response.status_code = info.status_code
    content = info.content
    if content is None:
        content = b''
    elif isinstance(content, str):
        content = content.encode('utf-8')
    response._content = content
    response._content_consumed = True
    if isinstance(info.headers, dict):
        response.headers.update(info.headers)
    response.url = url
    response.encoding = requests.utils.get_encoding_from_headers(response.headers)
    try:
        response.reason = HTTPStatus(info.status_code).phrase
    except ValueError:
        response.reason = ""
    return response


def _run_coroutine_sync(factory: Callable[[], Awaitable[Any]]) -> Any:
    """
    Runs a coroutine to completion from synchronous code.

    Works both when no event loop is running (uses asyncio.run) and when called
    from inside a running loop (runs the coroutine on a helper thread with its
    own loop, so the caller's loop is not re-entered).
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(factory())

    result: Dict[str, Any] = {}

    def runner():
        try:
            result['value'] = asyncio.run(factory())
        except BaseException as e:  # propagate to caller thread
            result['error'] = e

    thread = threading.Thread(target=runner, name="apikeyrotator-provider", daemon=True)
    thread.start()
    thread.join()
    if 'error' in result:
        raise result['error']
    return result.get('value')


def _setup_default_logger() -> logging.Logger:
    logger = logging.getLogger(__name__)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


# ============================================================================
# THREAD-SAFE KEY MANAGER
# ============================================================================

class _ThreadSafeKeyManager:
    """Simplified thread-safe key manager."""

    def __init__(self, keys: List[str], logger: logging.Logger):
        self._lock = threading.RLock()
        self._keys = keys.copy()
        self._key_metrics: Dict[str, KeyMetrics] = {
            key: KeyMetrics(key) for key in self._keys
        }
        self.logger = logger

    def get_keys(self) -> List[str]:
        with self._lock:
            return self._keys.copy()

    def get_key_count(self) -> int:
        with self._lock:
            return len(self._keys)

    def remove_key(self, key: str) -> bool:
        with self._lock:
            if key in self._keys:
                self._keys.remove(key)
                # Copy-on-write: the metrics dict is never mutated in place, so
                # readers can use it without copying (see get_metrics_view()).
                metrics = dict(self._key_metrics)
                metrics.pop(key, None)
                self._key_metrics = metrics
                return True
            return False

    def get_metrics(self, key: Optional[str] = None) -> Dict[str, Dict]:
        with self._lock:
            if key:
                if key in self._key_metrics:
                    return {key: self._key_metrics[key].to_dict()}
                return {}
            return {k: v.to_dict() for k, v in self._key_metrics.items()}

    def get_metric_objects(self) -> Dict[str, KeyMetrics]:
        with self._lock:
            return self._key_metrics.copy()

    def get_metrics_view(self) -> Dict[str, KeyMetrics]:
        """
        Current metrics dict without copying (hot path). The dict is replaced,
        never mutated, when keys change - callers must treat it as read-only.
        """
        return self._key_metrics

    def update_metrics(self, key: str, success: bool, response_time: float, is_rate_limited: bool = False) -> None:
        with self._lock:
            metrics = self._key_metrics.get(key)
        if metrics is not None:
            # KeyMetrics has its own lock - don't hold the manager lock while updating
            metrics.update_from_request(
                success=success,
                response_time=response_time,
                is_rate_limited=is_rate_limited
            )

    def mark_rate_limited(self, key: str, until: float) -> None:
        with self._lock:
            metrics = self._key_metrics.get(key)
        if metrics is not None:
            metrics.mark_rate_limited(until)

    def reset_health(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key:
                targets = [self._key_metrics[key]] if key in self._key_metrics else []
            else:
                targets = list(self._key_metrics.values())
        for metrics in targets:
            with metrics._lock:
                metrics.is_healthy = True
                metrics.consecutive_failures = 0
                metrics.rate_limit_reset = 0.0

    def reinit_keys(self, new_keys: List[str]) -> None:
        """Replaces the key list, preserving metrics of keys that are kept."""
        with self._lock:
            self._keys = new_keys.copy()
            self._key_metrics = {
                key: self._key_metrics.get(key) or KeyMetrics(key) for key in self._keys
            }


# ============================================================================
# BASE ROTATOR
# ============================================================================

class BaseKeyRotator:
    def __init__(
            self,
            api_keys: Optional[Union[List[str], str]] = None,
            env_var: str = "API_KEYS",
            max_retries: int = 3,
            base_delay: float = 1.0,
            timeout: float = 10.0,
            should_retry_callback: Optional[Callable[[Union[requests.Response, int]], bool]] = None,
            header_callback: Optional[Callable[[str, Optional[dict]], Union[dict, Tuple[dict, dict]]]] = None,
            user_agents: Optional[List[str]] = None,
            random_delay_range: Optional[Tuple[float, float]] = None,
            proxy_list: Optional[List[str]] = None,
            logger: Optional[logging.Logger] = None,
            config_file: str = "rotator_config.json",
            load_env_file: bool = True,
            error_classifier: Optional[ErrorClassifier] = None,
            config_loader: Optional[ConfigLoader] = None,
            rotation_strategy: Union[str, RotationStrategy, BaseRotationStrategy] = "round_robin",
            rotation_strategy_kwargs: Optional[Dict] = None,
            middlewares: Optional[List[RotatorMiddleware]] = None,
            secret_provider: Optional[SecretProvider] = None,
            enable_metrics: bool = True,
            save_sensitive_headers: bool = False,
            max_delay: float = DEFAULT_MAX_DELAY,
            pool_size: int = DEFAULT_POOL_SIZE,
            recovery_timeout: Optional[float] = None,
    ):
        """
        Args:
            max_delay: Upper bound (seconds) for any single retry/backoff wait.
            pool_size: Maximum number of pooled HTTP connections.
            recovery_timeout: Seconds after the last failure when an unhealthy key is
                              probed again. None keeps the strategy default (60s).
            (other arguments are documented in docs/API_REFERENCE.md)
        """
        self.logger = logger if logger else _setup_default_logger()

        if load_env_file and _DOTENV_INSTALLED:
            load_dotenv()

        if max_retries < 1:
            raise ValueError("max_retries must be >= 1")

        self.secret_provider = secret_provider

        if api_keys is None and secret_provider is not None:
            provider_keys = _run_coroutine_sync(secret_provider.get_keys)
            if provider_keys:
                api_keys = list(provider_keys)
            else:
                self.logger.warning("Secret provider returned no keys, falling back to environment variable")

        keys = parse_keys(api_keys, env_var, self.logger)
        if not keys:
            raise ValueError("At least one API key is required")

        self.key_manager = _ThreadSafeKeyManager(keys, self.logger)

        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.timeout = timeout
        self.pool_size = max(1, int(pool_size))
        self.should_retry_callback = should_retry_callback
        self.header_callback = header_callback
        self.config_file = config_file
        self.save_sensitive_headers = save_sensitive_headers
        self.error_classifier = error_classifier or ErrorClassifier()
        self.random_delay_range = random_delay_range
        self.user_agents = user_agents or []
        self._ua_index = 0
        self.proxy_list = proxy_list or []
        self._proxy_index = 0
        self._cycle_lock = threading.Lock()

        self.config_loader = config_loader or ConfigLoader(config_file=config_file, logger=self.logger)
        self.config = self.config_loader.load_config()

        self.rotation_strategy_kwargs = rotation_strategy_kwargs or {}
        self._init_rotation_strategy(rotation_strategy)
        if recovery_timeout is not None:
            self.rotation_strategy.recovery_timeout = recovery_timeout

        self.middlewares = middlewares or []
        self.enable_metrics = enable_metrics
        self.metrics = RotatorMetrics() if enable_metrics else None

        self._log_initialization_summary()

    def _init_rotation_strategy(self, rotation_strategy: Union[str, RotationStrategy, BaseRotationStrategy]) -> None:
        if isinstance(rotation_strategy, BaseRotationStrategy):
            self.rotation_strategy = rotation_strategy
            return

        strategy_name = (
            rotation_strategy.value if isinstance(rotation_strategy, RotationStrategy)
            else str(rotation_strategy).lower()
        )
        kwargs = dict(self.rotation_strategy_kwargs)
        keys: Union[List[str], Dict[str, float]] = self.key_manager.get_keys()

        if strategy_name == "weighted":
            # Weighted strategy needs {key: weight}; default to equal weights
            weights = kwargs.pop("weights", None) or {}
            keys = {k: float(weights.get(k, 1.0)) for k in keys}

        self.rotation_strategy = create_rotation_strategy(strategy_name, keys, **kwargs)

    def _log_initialization_summary(self) -> None:
        self.logger.info(
            f"✅ Rotator initialized with {self.key_manager.get_key_count()} keys. "
            f"Max retries: {self.max_retries}, Base delay: {self.base_delay}s, "
            f"Strategy: {type(self.rotation_strategy).__name__}"
        )
        if self.middlewares:
            self.logger.info(f"✅ Middlewares loaded: {len(self.middlewares)}")

    # ------------------------------------------------------------------
    # Keys management
    # ------------------------------------------------------------------

    @property
    def keys(self) -> List[str]:
        return self.key_manager.get_keys()

    @keys.setter
    def keys(self, new_keys: List[str]):
        cleaned = parse_keys(list(new_keys), logger=self.logger)
        self.key_manager.reinit_keys(cleaned)
        if hasattr(self.rotation_strategy, 'update_keys'):
            self.rotation_strategy.update_keys(cleaned)

    @property
    def _key_metrics(self) -> Dict[str, KeyMetrics]:
        return self.key_manager.get_metric_objects()

    @property
    def key_count(self) -> int:
        return self.key_manager.get_key_count()

    def _remove_key(self, key: str) -> None:
        if self.key_manager.remove_key(key) and hasattr(self.rotation_strategy, 'update_keys'):
            self.rotation_strategy.update_keys(self.key_manager.get_keys())

    async def refresh_keys_from_provider(self) -> List[str]:
        """
        Reloads keys from the configured secret provider.

        Metrics of keys that are still present are preserved. If the provider
        returns no keys, the current keys are kept.

        Returns:
            List[str]: The active key list after refresh
        """
        if self.secret_provider is None:
            raise ValueError("No secret_provider configured")
        new_keys = await self.secret_provider.refresh_keys()
        if not new_keys:
            self.logger.warning("Secret provider returned no keys; keeping current keys")
            return self.keys
        self.keys = list(new_keys)
        self.logger.info(f"🔄 Keys refreshed from provider: {self.key_count} keys active")
        return self.keys

    def refresh_keys_from_provider_sync(self) -> List[str]:
        """Synchronous version of refresh_keys_from_provider()."""
        return _run_coroutine_sync(self.refresh_keys_from_provider)

    def get_metrics(self) -> Dict:
        return self.metrics.get_metrics() if self.metrics else {}

    def get_key_statistics(self) -> Dict:
        return self.key_manager.get_metrics()

    def reset_key_health(self, key: Optional[str] = None):
        self.key_manager.reset_health(key)

    def export_config(self) -> Dict[str, Any]:
        config = {
            'keys_count': self.key_manager.get_key_count(),
            'max_retries': self.max_retries,
            'base_delay': self.base_delay,
            'max_delay': self.max_delay,
            'timeout': self.timeout,
            'strategy': self.rotation_strategy.__class__.__name__,
            'metrics_enabled': self.metrics is not None,
        }
        if self.metrics:
            config['key_statistics'] = {}
            for index, (key, key_metrics) in enumerate(self.key_manager.get_metrics().items()):
                safe_key = f"{key[:4]}****" if len(key) > 4 else "****"
                if safe_key in config['key_statistics']:
                    safe_key = f"{safe_key}#{index}"
                config['key_statistics'][safe_key] = key_metrics
        return config

    # ------------------------------------------------------------------
    # Request preparation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_url(url: str) -> None:
        if not url or not url.strip():
            raise ValueError("URL cannot be empty")

    @staticmethod
    def _get_domain_from_url(url: str) -> str:
        try:
            return urlsplit(url).netloc
        except (ValueError, AttributeError):
            return ""

    @staticmethod
    def _endpoint_label(url: str) -> str:
        """URL without query string/fragment - keeps endpoint metrics bounded."""
        try:
            parts = urlsplit(url)
            return urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))
        except (ValueError, AttributeError):
            return url

    def _infer_auth_header(self, key: str) -> Tuple[str, str]:
        for prefix in API_KEY_PATTERNS['bearer']:
            if key.startswith(prefix):
                return DEFAULT_AUTH_HEADERS['bearer'], f"Bearer {key}"
        if len(key) == API_KEY_PATTERNS['api_key']:
            return DEFAULT_AUTH_HEADERS['api_key'], key
        return DEFAULT_AUTH_HEADERS['bearer'], f"Key {key}"

    def get_next_key(self) -> str:
        if self.key_manager.get_key_count() == 0:
            raise AllKeysExhaustedError("No valid keys available")

        metrics_objects = self.key_manager.get_metrics_view()
        try:
            key = self.rotation_strategy.get_next_key(metrics_objects)
        except ValueError as e:
            raise AllKeysExhaustedError(f"No valid keys available: {e}") from e

        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug("Selected key: %s", _mask_key(key))
        return key

    def get_next_user_agent(self) -> Optional[str]:
        if not self.user_agents:
            return None
        with self._cycle_lock:
            ua = self.user_agents[self._ua_index % len(self.user_agents)]
            self._ua_index = (self._ua_index + 1) % len(self.user_agents)
        return ua

    def get_next_proxy(self) -> Optional[str]:
        if not self.proxy_list:
            return None
        with self._cycle_lock:
            proxy = self.proxy_list[self._proxy_index % len(self.proxy_list)]
            self._proxy_index = (self._proxy_index + 1) % len(self.proxy_list)
        return proxy

    def _prepare_headers_and_cookies(
            self, key: str, custom_headers: Optional[Dict[str, str]], url: str
    ) -> Tuple[Dict[str, str], Dict[str, str]]:
        headers = dict(custom_headers) if custom_headers else {}
        cookies: Dict[str, str] = {}

        if self.save_sensitive_headers:
            domain = self._get_domain_from_url(url)
            if domain:
                saved = self.config.get("successful_headers", {}).get(domain, {})
                safe_headers = {
                    k: v for k, v in saved.items() if k.lower() not in ("authorization", "x-api-key")
                }
                headers.update(safe_headers)

        if self.header_callback:
            result = self.header_callback(key, custom_headers)
            if isinstance(result, tuple) and len(result) == 2:
                headers.update(result[0])
                cookies.update(result[1])
            elif isinstance(result, dict):
                headers.update(result)

        present = {h.lower() for h in headers}
        if "authorization" not in present:
            header_name, header_value = self._infer_auth_header(key)
            if header_name.lower() not in present:
                headers[header_name] = header_value

        if "user-agent" not in present:
            user_agent = self.get_next_user_agent()
            if user_agent:
                headers["User-Agent"] = user_agent

        return headers, cookies

    def _prepare_request(
            self, method: str, url: str, key: str, kwargs: Dict[str, Any], attempt: int, is_async: bool
    ) -> Tuple[Dict[str, Any], RequestInfo]:
        headers, cookies = self._prepare_headers_and_cookies(key, kwargs.get("headers"), url)

        request_kwargs = dict(kwargs)
        request_kwargs["headers"] = headers
        user_cookies = kwargs.get("cookies")
        if isinstance(user_cookies, dict):
            cookies = {**user_cookies, **cookies}
        request_kwargs["cookies"] = cookies

        proxy = self.get_next_proxy()
        if is_async:
            timeout = kwargs.get("timeout")
            if isinstance(timeout, (int, float)):
                request_kwargs["timeout"] = aiohttp.ClientTimeout(total=timeout)
            if proxy:
                request_kwargs["proxy"] = proxy
        else:
            request_kwargs["timeout"] = kwargs.get("timeout", self.timeout)
            if proxy:
                request_kwargs["proxies"] = {"http": proxy, "https": proxy}

        request_info = RequestInfo(
            method=method, url=url, headers=headers, cookies=cookies,
            key=key, attempt=attempt, kwargs=request_kwargs
        )
        return request_kwargs, request_info

    # ------------------------------------------------------------------
    # Delays
    # ------------------------------------------------------------------

    def _random_delay_value(self) -> float:
        if not self.random_delay_range:
            return 0.0
        delay = random.uniform(self.random_delay_range[0], self.random_delay_range[1])
        return delay + random.uniform(0, delay * 0.1)

    def _apply_random_delay(self) -> None:
        if self.random_delay_range:
            time.sleep(self._random_delay_value())

    async def _apply_random_delay_async(self) -> None:
        if self.random_delay_range:
            await asyncio.sleep(self._random_delay_value())

    def _calculate_backoff_delay(self, attempt: int) -> float:
        # Cap the exponent too, to avoid float overflow for huge max_retries
        delay = min(self.base_delay * (2 ** min(attempt, 30)), self.max_delay)
        return min(delay + random.uniform(0, delay * 0.1), self.max_delay)

    def _recovery_timeout(self) -> Optional[float]:
        return getattr(self.rotation_strategy, 'recovery_timeout', None)

    def _has_available_key(self) -> bool:
        now = time.time()
        recovery_timeout = self._recovery_timeout()
        return any(
            m.is_available(now, recovery_timeout)
            for m in self.key_manager.get_metrics_view().values()
        )

    def _time_until_key_available(self) -> Optional[float]:
        """Seconds until the earliest rate-limited key becomes usable again (None if unknown)."""
        now = time.time()
        waits = [
            m.rate_limit_reset - now
            for m in self.key_manager.get_metrics_view().values()
            if m.rate_limit_reset > now
        ]
        return min(waits) if waits else None

    def _retry_delay(self, attempt: int, error_type: Optional[ErrorType], headers: Optional[Dict[str, str]]) -> float:
        """
        Computes how long to wait before the next attempt.

        - Rate limit: switch to another available key immediately; if every key
          is rate limited, wait until the earliest one frees up (bounded by max_delay).
        - Temporary server error: honour Retry-After, else exponential backoff.
        - Network error / other: exponential backoff.
        """
        backoff = self._calculate_backoff_delay(attempt)
        if error_type == ErrorType.RATE_LIMIT:
            if self._has_available_key():
                return 0.0
            wait = self._time_until_key_available()
            if wait is not None:
                return min(max(wait, 0.0), self.max_delay)
            return backoff
        if error_type == ErrorType.TEMPORARY:
            retry_after = parse_retry_after(headers)
            if retry_after is not None:
                return min(retry_after, self.max_delay)
        return backoff

    # ------------------------------------------------------------------
    # Response handling (shared by sync/async)
    # ------------------------------------------------------------------

    def _record(
            self, key: str, endpoint: str, success: bool, request_time: float,
            is_rate_limited: bool = False, key_success: Optional[bool] = None
    ) -> None:
        if self.metrics:
            self.metrics.record_request(
                key=key, endpoint=endpoint, success=success,
                response_time=request_time, is_rate_limited=is_rate_limited
            )
        self.key_manager.update_metrics(
            key, success if key_success is None else key_success, request_time, is_rate_limited
        )

    def _handle_response(
            self,
            key: str,
            endpoint: str,
            status_code: int,
            headers: Dict[str, str],
            classifier_response: Any,
            callback_arg: Any,
            request_time: float,
            attempt: int,
    ) -> Tuple[_Action, Optional[ErrorType]]:
        error_type = self.error_classifier.classify_error(response=classifier_response)

        if error_type == ErrorType.PERMANENT:
            if self.error_classifier.should_remove_key(classifier_response):
                self._record(key, endpoint, False, request_time)
                self.logger.error(
                    f"❌ Key {_mask_key(key)} permanently invalid (Status: {status_code}). Removing it from rotation.")
                self._remove_key(key)
                return _Action.SWITCH, error_type
            # Client error (400/404/422...) - the request is wrong, not the key.
            # Retrying or removing the key would not help: hand the response back.
            self._record(key, endpoint, False, request_time, key_success=True)
            self.logger.warning(f"⚠️ Client error (Status: {status_code}), not retrying")
            return _Action.RETURN, error_type

        if error_type in (ErrorType.RATE_LIMIT, ErrorType.TEMPORARY):
            is_rate_limited = error_type == ErrorType.RATE_LIMIT
            self._record(key, endpoint, False, request_time, is_rate_limited=is_rate_limited)
            if is_rate_limited:
                retry_after = parse_retry_after(headers)
                if retry_after is None:
                    retry_after = self._calculate_backoff_delay(attempt)
                self.key_manager.mark_rate_limited(key, time.time() + retry_after)
            msg = "Rate limited" if is_rate_limited else "Temporary error"
            self.logger.warning(
                f"↻ {msg} (Status: {status_code}, key: {_mask_key(key)}). "
                f"Attempt {attempt + 1}/{self.max_retries}")
            return _Action.RETRY, error_type

        if self.should_retry_callback and self.should_retry_callback(callback_arg):
            self._record(key, endpoint, False, request_time)
            self.logger.warning(
                f"↻ Retry requested by should_retry_callback (Status: {status_code}). "
                f"Attempt {attempt + 1}/{self.max_retries}")
            return _Action.RETRY, None

        self._record(key, endpoint, True, request_time)
        self.logger.debug("✅ Success (Status: %s)", status_code)
        return _Action.RETURN, None

    def _exhausted_error(self, last_response: Any, last_exception: Optional[BaseException]) -> AllKeysExhaustedError:
        self.logger.error(f"❌ All {self.max_retries} retries exhausted")
        details = ""
        if last_exception is not None:
            details = f" Last error: {type(last_exception).__name__}: {last_exception}"
        elif last_response is not None:
            status = getattr(last_response, 'status_code', getattr(last_response, 'status', None))
            details = f" Last status: {status}"
        return AllKeysExhaustedError(
            f"All keys exhausted after {self.max_retries} attempts.{details}",
            last_response=last_response,
            last_exception=last_exception,
        )


# ============================================================================
# SYNC ROTATOR
# ============================================================================

class APIKeyRotator(BaseKeyRotator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=self.pool_size, pool_maxsize=self.pool_size, max_retries=0
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.logger.info("✅ Sync rotator initialized with Connection Pooling")

    def close(self) -> None:
        """Closes the underlying HTTP session and its connection pool."""
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # --- middleware helpers ---

    def _run_before_request(self, request_info: RequestInfo, request_kwargs: Dict[str, Any]) -> Optional[ResponseInfo]:
        for middleware in self.middlewares:
            hook = getattr(middleware, 'before_request_sync', None)
            if hook is None:
                continue
            result = hook(request_info)
            if isinstance(result, ResponseInfo):
                return result
            if isinstance(result, RequestInfo):
                request_info = result
                request_kwargs["headers"] = request_info.headers
                request_kwargs["cookies"] = request_info.cookies
        return None

    def _run_after_request(self, response_info: ResponseInfo) -> None:
        for middleware in self.middlewares:
            hook = getattr(middleware, 'after_request_sync', None)
            if hook is not None:
                result = hook(response_info)
                if isinstance(result, ResponseInfo):
                    response_info = result

    def _run_on_error(self, error_info: ErrorInfo) -> None:
        for middleware in self.middlewares:
            hook = getattr(middleware, 'on_error_sync', None)
            if hook is None:
                continue
            try:
                hook(error_info)
            except Exception as e:  # a faulty middleware must not break the retry loop
                self.logger.warning(f"Middleware {type(middleware).__name__}.on_error_sync failed: {e}")

    # --- request ---

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        self._validate_url(url)

        self.logger.debug("Initiating %s request to %s", method, url)
        endpoint = self._endpoint_label(url)
        stream = bool(kwargs.get("stream"))

        retry_attempt = 0
        last_response: Optional[requests.Response] = None
        last_exception: Optional[BaseException] = None

        while True:
            if retry_attempt >= self.max_retries:
                raise self._exhausted_error(last_response, last_exception)

            if self.key_count == 0:
                raise AllKeysExhaustedError(
                    "All keys are invalid (empty list)",
                    last_response=last_response, last_exception=last_exception,
                )

            key = self.get_next_key()
            request_kwargs, request_info = self._prepare_request(
                method, url, key, kwargs, retry_attempt, is_async=False
            )

            if self.middlewares:
                short_circuit = self._run_before_request(request_info, request_kwargs)
                if short_circuit is not None:
                    return _build_sync_response(short_circuit, url)

            self._apply_random_delay()

            start_time = time.monotonic()
            try:
                response = self.session.request(method, url, **request_kwargs)
            except requests.RequestException as e:
                request_time = time.monotonic() - start_time
                last_exception = e
                self._record(key, endpoint, False, request_time)
                if self.middlewares:
                    self._run_on_error(ErrorInfo(exception=e, request_info=request_info))
                retry_attempt += 1
                self.logger.warning(f"⚠️ Network error: {e}. Attempt {retry_attempt}/{self.max_retries}")
                if retry_attempt < self.max_retries:
                    time.sleep(self._calculate_backoff_delay(retry_attempt - 1))
                continue

            request_time = time.monotonic() - start_time
            response_headers = dict(response.headers)

            response_info = None
            if self.middlewares:
                response_info = ResponseInfo(
                    status_code=response.status_code, headers=response_headers,
                    content=None if stream else response.content,
                    request_info=request_info, response_time=request_time,
                )
                self._run_after_request(response_info)

            action, error_type = self._handle_response(
                key, endpoint, response.status_code, response_headers,
                classifier_response=response, callback_arg=response,
                request_time=request_time, attempt=retry_attempt,
            )

            if action is _Action.RETURN:
                if last_response is not None:
                    last_response.close()
                return response

            if response_info is not None:
                self._run_on_error(ErrorInfo(
                    exception=HTTPStatusError(response.status_code),
                    request_info=request_info, response_info=response_info,
                ))

            # Release the previous failed response's connection before keeping this one
            if last_response is not None:
                last_response.close()
            last_response = response
            last_exception = None

            if action is _Action.SWITCH:
                continue

            retry_attempt += 1
            if retry_attempt < self.max_retries:
                delay = self._retry_delay(retry_attempt - 1, error_type, response_headers)
                if delay > 0:
                    time.sleep(delay)

    def get(self, url: str, **kwargs) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> requests.Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs) -> requests.Response:
        return self.request("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs) -> requests.Response:
        return self.request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs) -> requests.Response:
        return self.request("DELETE", url, **kwargs)

    def head(self, url: str, **kwargs) -> requests.Response:
        return self.request("HEAD", url, **kwargs)


# ============================================================================
# ASYNC ROTATOR
# ============================================================================

async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


class AsyncAPIKeyRotator(BaseKeyRotator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._session: Optional[aiohttp.ClientSession] = None
        self.logger.info("✅ Async rotator initialized")

    async def __aenter__(self):
        await self._get_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self) -> None:
        """Closes the underlying aiohttp session."""
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(limit=self.pool_size)
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                connector=connector,
            )
        return self._session

    @staticmethod
    async def _release(response: Any) -> None:
        release = getattr(response, 'release', None)
        if release is not None:
            try:
                await _maybe_await(release())
            except Exception:
                pass

    # --- middleware helpers ---

    async def _run_before_request(
            self, request_info: RequestInfo, request_kwargs: Dict[str, Any]
    ) -> Optional[ResponseInfo]:
        for middleware in self.middlewares:
            hook = getattr(middleware, 'before_request', None)
            if hook is None:
                continue
            result = await _maybe_await(hook(request_info))
            if isinstance(result, ResponseInfo):
                return result
            if isinstance(result, RequestInfo):
                request_info = result
                request_kwargs["headers"] = request_info.headers
                request_kwargs["cookies"] = request_info.cookies
        return None

    async def _run_after_request(self, response_info: ResponseInfo) -> None:
        for middleware in self.middlewares:
            hook = getattr(middleware, 'after_request', None)
            if hook is not None:
                result = await _maybe_await(hook(response_info))
                if isinstance(result, ResponseInfo):
                    response_info = result

    async def _run_on_error(self, error_info: ErrorInfo) -> None:
        for middleware in self.middlewares:
            hook = getattr(middleware, 'on_error', None)
            if hook is None:
                continue
            try:
                await _maybe_await(hook(error_info))
            except Exception as e:  # a faulty middleware must not break the retry loop
                self.logger.warning(f"Middleware {type(middleware).__name__}.on_error failed: {e}")

    # --- request ---

    async def request(self, method: str, url: str, **kwargs) -> aiohttp.ClientResponse:
        self._validate_url(url)

        self.logger.debug("Initiating async %s request to %s", method, url)
        session = await self._get_session()
        endpoint = self._endpoint_label(url)

        retry_attempt = 0
        last_response: Any = None
        last_exception: Optional[BaseException] = None

        while True:
            if retry_attempt >= self.max_retries:
                raise self._exhausted_error(last_response, last_exception)

            if self.key_count == 0:
                raise AllKeysExhaustedError(
                    "All keys are invalid",
                    last_response=last_response, last_exception=last_exception,
                )

            key = self.get_next_key()
            request_kwargs, request_info = self._prepare_request(
                method, url, key, kwargs, retry_attempt, is_async=True
            )

            if self.middlewares:
                short_circuit = await self._run_before_request(request_info, request_kwargs)
                if short_circuit is not None:
                    return _CachedAsyncResponse(
                        short_circuit.status_code, short_circuit.headers, short_circuit.content, url
                    )

            await self._apply_random_delay_async()

            start_time = time.monotonic()
            try:
                response = await session.request(method, url, **request_kwargs)
                request_time = time.monotonic() - start_time
                response_headers = dict(response.headers)

                response_info = None
                if self.middlewares:
                    # Read the body so middlewares (e.g. caching) can see it;
                    # aiohttp caches it, so the caller can still read()/json() it.
                    content = await response.read()
                    response_info = ResponseInfo(
                        status_code=response.status, headers=response_headers,
                        content=content, request_info=request_info, response_time=request_time,
                    )
                    await self._run_after_request(response_info)
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                request_time = time.monotonic() - start_time
                last_exception = e
                self._record(key, endpoint, False, request_time)
                if self.middlewares:
                    await self._run_on_error(ErrorInfo(exception=e, request_info=request_info))
                retry_attempt += 1
                self.logger.warning(
                    f"⚠️ Async network error: {type(e).__name__}: {e}. Attempt {retry_attempt}/{self.max_retries}")
                if retry_attempt < self.max_retries:
                    await asyncio.sleep(self._calculate_backoff_delay(retry_attempt - 1))
                continue

            action, error_type = self._handle_response(
                key, endpoint, response.status, response_headers,
                classifier_response=_ResponseCodeWrapper(response.status, response_headers),
                callback_arg=response.status,
                request_time=request_time, attempt=retry_attempt,
            )

            if action is _Action.RETURN:
                return response

            if response_info is not None:
                await self._run_on_error(ErrorInfo(
                    exception=HTTPStatusError(response.status),
                    request_info=request_info, response_info=response_info,
                ))

            # Failed responses are released immediately so the connection returns
            # to the pool; the last one is still exposed via AllKeysExhaustedError.
            await self._release(response)
            last_response = response
            last_exception = None

            if action is _Action.SWITCH:
                continue

            retry_attempt += 1
            if retry_attempt < self.max_retries:
                delay = self._retry_delay(retry_attempt - 1, error_type, response_headers)
                if delay > 0:
                    await asyncio.sleep(delay)

    async def get(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        return await self.request("PUT", url, **kwargs)

    async def patch(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        return await self.request("PATCH", url, **kwargs)

    async def delete(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        return await self.request("DELETE", url, **kwargs)

    async def head(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        return await self.request("HEAD", url, **kwargs)
