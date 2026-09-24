from __future__ import annotations
import asyncio
import json
import logging
import random
import threading
import time
import weakref
from collections.abc import Awaitable, Callable
from enum import Enum
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

from apikeyrotator.metrics import RotatorMetrics
from apikeyrotator.middleware import ErrorInfo, RequestInfo, ResponseInfo, RotatorMiddleware
from apikeyrotator.providers import SecretProvider
from apikeyrotator.state import InMemoryStateBackend, SharedState, StateBackend
from apikeyrotator.strategies import (
    BaseRotationStrategy,
    KeyMetrics,
    RotationStrategy,
    create_rotation_strategy,
)
from apikeyrotator.utils import (
    CircuitBreaker,
    CircuitBreakerConfig,
    ErrorClassifier,
    ErrorType,
    get_header,
    parse_rate_limit_headers,
    parse_retry_after,
)

from .config_loader import ConfigLoader
from .exceptions import (
    AllKeysExhaustedError,
    CircuitOpenError,
    DeadlineExceededError,
    HTTPStatusError,
)
from .key_parser import parse_keys
from .transport import (
    AsyncTransport,
    SyncTransport,
    create_async_transport,
    create_sync_transport,
)


if TYPE_CHECKING:  # HTTP libraries are imported lazily by the transports
    import aiohttp
    import requests

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

#: RFC 9110 idempotent methods - safe to retry after any failure
IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE", "TRACE"})
#: Statuses meaning "the request was not processed" - safe to retry even for POST/PATCH
NON_IDEMPOTENT_RETRYABLE_STATUSES = frozenset({408, 425, 429, 503})


def _mask_key(key: str) -> str:
    return f"{key[:KEY_LOG_LENGTH]}{KEY_LOG_SUFFIX}"


def _endpoint_label(url: str) -> str:
    """URL without query string/fragment - keeps endpoint metrics bounded (no urlsplit allocations)."""
    cut = len(url)
    for ch in ('?', '#'):
        i = url.find(ch)
        if i != -1 and i < cut:
            cut = i
    return url[:cut] if cut != len(url) else url


def _host_of(url: str) -> str:
    """Host[:port] of a URL (lower-cased), used as circuit breaker scope."""
    start = url.find('://')
    rest = url[start + 3:] if start != -1 else url
    end = len(rest)
    for ch in ('/', '?', '#'):
        i = rest.find(ch, 0, end)
        if i != -1:
            end = i
    host = rest[:end]
    if '@' in host:
        host = host.rsplit('@', 1)[1]
    return host.lower()


class _ResponseCodeWrapper:
    """Wrapper for status code to simulate response object behavior for classifier"""
    __slots__ = ('status_code', 'headers')

    def __init__(self, status_code: int, headers: Any = None):
        self.status_code = status_code
        self.headers = headers if headers is not None else {}


class _Action(Enum):
    """What the request loop should do after a response was classified."""
    RETURN = "return"  # hand the response to the caller
    RETRY = "retry"  # retry (consumes one attempt)
    SWITCH = "switch"  # key was removed, retry with another key (no attempt consumed)


class _RequestContext:
    """Per-request state of the retry loop."""
    __slots__ = (
        'method', 'url', 'endpoint', 'idempotent', 'deadline', 'attempt',
        'last_response', 'last_exception', 'reports', 'breaker', 'breaker_pending',
    )

    def __init__(self, method: str, url: str, idempotent: bool, deadline: float | None,
                 breaker: CircuitBreaker | None):
        self.method = method
        self.url = url
        self.endpoint = _endpoint_label(url)
        self.idempotent = idempotent
        self.deadline = deadline
        self.attempt = 0
        self.last_response: Any = None
        self.last_exception: BaseException | None = None
        # Deferred writes to the state backend: (method_name, args). Flushed by the
        # sync/async loop so the async rotator never blocks the event loop on I/O.
        self.reports: list[tuple[str, tuple]] = []
        self.breaker = breaker
        # True between allow_request() and a verdict (success/failure): if the attempt
        # dies in between, the HALF_OPEN probe slot must be released (see finish()).
        self.breaker_pending = False

    def breaker_verdict(self, success: bool) -> None:
        breaker = self.breaker
        if breaker is not None:
            self.breaker_pending = False
            if success:
                breaker.record_success()
            else:
                breaker.record_failure()

    def release_breaker(self) -> None:
        if self.breaker_pending:
            self.breaker_pending = False
            self.breaker.release_probe()

    def remaining(self) -> float | None:
        if self.deadline is None:
            return None
        return self.deadline - time.monotonic()


class _CachedAsyncResponse:
    """
    Minimal aiohttp/httpx-like response returned for middleware short-circuits
    (e.g. cache hits). Exposes both ``status`` (aiohttp) and ``status_code`` (httpx).
    """

    def __init__(self, status: int, headers: Any, content: Any, url: str = ""):
        self.status = status
        self.headers = dict(headers or {})
        self.url = url
        if content is None:
            content = b''
        self._content = content if isinstance(content, bytes) else str(content).encode('utf-8')

    @property
    def status_code(self) -> int:
        return self.status

    @property
    def content(self) -> bytes:
        return self._content

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

    async def aread(self) -> bytes:
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

    async def aclose(self) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


def _build_sync_response(info: ResponseInfo, url: str, backend: str = "requests") -> Any:
    """Builds a response object from a middleware-provided ResponseInfo (e.g. cache hit)."""
    content = info.content
    if content is None:
        content = b''
    elif isinstance(content, str):
        content = content.encode('utf-8')
    headers = info.headers if isinstance(info.headers, dict) else {}

    if backend == "httpx":
        import httpx

        return httpx.Response(info.status_code, headers=headers, content=content,
                              request=httpx.Request("GET", url))

    import requests
    import requests.utils

    response = requests.Response()
    response.status_code = info.status_code
    response._content = content
    response._content_consumed = True
    response.headers.update(headers)
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

    result: dict[str, Any] = {}

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
    """Library logger - output is configured by the application (logging.basicConfig())."""
    return logging.getLogger(__name__)


# ============================================================================
# THREAD-SAFE KEY MANAGER
# ============================================================================

class _ThreadSafeKeyManager:
    """
    Thread-safe key list + per-key metrics.

    The metrics dict is copy-on-write: it is replaced, never mutated, so the hot
    path can read it without a lock or a copy (get_metrics_view()).
    """

    __slots__ = ('_lock', '_keys', '_key_metrics', 'logger')

    def __init__(self, keys: list[str], logger: logging.Logger):
        self._lock = threading.Lock()
        self._keys = keys.copy()
        self._key_metrics: dict[str, KeyMetrics] = {key: KeyMetrics(key) for key in self._keys}
        self.logger = logger

    def get_keys(self) -> list[str]:
        with self._lock:
            return self._keys.copy()

    def get_key_count(self) -> int:
        return len(self._key_metrics)

    def remove_key(self, key: str) -> bool:
        with self._lock:
            if key not in self._key_metrics:
                return False
            self._keys.remove(key)
            metrics = dict(self._key_metrics)
            del metrics[key]
            self._key_metrics = metrics
            return True

    def get_metrics(self, key: str | None = None) -> dict[str, dict]:
        metrics = self._key_metrics
        if key:
            m = metrics.get(key)
            return {key: m.to_dict()} if m is not None else {}
        return {k: v.to_dict() for k, v in metrics.items()}

    def get_metric_objects(self) -> dict[str, KeyMetrics]:
        return dict(self._key_metrics)

    def get_metrics_view(self) -> dict[str, KeyMetrics]:
        """Current metrics dict without copying (read-only for callers)."""
        return self._key_metrics

    def update_metrics(self, key: str, success: bool, response_time: float, is_rate_limited: bool = False) -> None:
        metrics = self._key_metrics.get(key)
        if metrics is not None:
            metrics.update_from_request(success, response_time, is_rate_limited)

    def mark_rate_limited(self, key: str, until: float) -> None:
        metrics = self._key_metrics.get(key)
        if metrics is not None:
            metrics.mark_rate_limited(until)

    def reset_health(self, key: str | None = None) -> None:
        metrics = self._key_metrics
        if key:
            targets = [metrics[key]] if key in metrics else []
        else:
            targets = list(metrics.values())
        for m in targets:
            with m._lock:
                m.is_healthy = True
                m.consecutive_failures = 0
                m.rate_limit_reset = 0.0

    def reinit_keys(self, new_keys: list[str]) -> None:
        """Replaces the key list, preserving metrics of keys that are kept."""
        with self._lock:
            old = self._key_metrics
            self._keys = new_keys.copy()
            self._key_metrics = {key: old.get(key) or KeyMetrics(key) for key in self._keys}


# ============================================================================
# BASE ROTATOR
# ============================================================================

class BaseKeyRotator:
    def __init__(
            self,
            api_keys: list[str] | str | None = None,
            env_var: str = "API_KEYS",
            max_retries: int = 3,
            base_delay: float = 1.0,
            timeout: float = 10.0,
            should_retry_callback: Callable[[Any], bool] | None = None,
            header_callback: Callable[[str, dict | None], dict | tuple[dict, dict]] | None = None,
            user_agents: list[str] | None = None,
            random_delay_range: tuple[float, float] | None = None,
            proxy_list: list[str] | None = None,
            logger: logging.Logger | None = None,
            config_file: str = "rotator_config.json",
            load_env_file: bool = True,
            error_classifier: ErrorClassifier | None = None,
            config_loader: ConfigLoader | None = None,
            rotation_strategy: str | RotationStrategy | BaseRotationStrategy = "round_robin",
            rotation_strategy_kwargs: dict | None = None,
            middlewares: list[RotatorMiddleware] | None = None,
            secret_provider: SecretProvider | None = None,
            enable_metrics: bool = True,
            save_sensitive_headers: bool = False,
            max_delay: float = DEFAULT_MAX_DELAY,
            pool_size: int = DEFAULT_POOL_SIZE,
            recovery_timeout: float | None = None,
            total_timeout: float | None = None,
            retry_non_idempotent: bool = False,
            circuit_breaker: bool | CircuitBreakerConfig | None = None,
            key_rate_limit: tuple[int, float] | None = None,
            respect_rate_limit_headers: bool = True,
            state_backend: StateBackend | None = None,
            state_sync_interval: float = 1.0,
            auto_refresh_interval: float | None = None,
    ):
        """
        Args:
            max_delay: Upper bound (seconds) for any single retry/backoff wait.
            pool_size: Maximum number of pooled HTTP connections.
            recovery_timeout: Seconds after the last failure when an unhealthy key is
                              probed again. None keeps the strategy default (60s).
            total_timeout: Time budget (seconds) of one request including all retries
                           and waits. Can be overridden per request (``total_timeout=``).
                           Raises DeadlineExceededError when spent.
            retry_non_idempotent: Retry POST/PATCH after failures where the request may
                                  already have been processed (5xx other than 503, read
                                  timeouts, dropped connections). Default False: only
                                  retry them when the server certainly didn't process the
                                  request (429/503/408/425, connection refused) or when an
                                  ``Idempotency-Key`` header is present.
            circuit_breaker: True or CircuitBreakerConfig to enable a per-host circuit
                             breaker - after repeated 5xx/network failures requests fail
                             fast with CircuitOpenError instead of hitting a dead host.
            key_rate_limit: (requests, per_seconds) client-side limit per key, e.g.
                            (60, 60) = 60 requests/minute/key (token bucket). Keys over
                            their limit are skipped before the server answers 429.
            respect_rate_limit_headers: Mark a key as limited when a response reports
                                        ``X-RateLimit-Remaining: 0`` (until its reset).
            state_backend: Shared state (e.g. RedisStateBackend) so several processes
                           see each other's rate-limited / invalid keys and share token
                           buckets.
            state_sync_interval: How often (seconds) shared state is pulled.
            auto_refresh_interval: Reload keys from ``secret_provider`` every N seconds
                                   in the background.
            (other arguments are documented in docs/API_REFERENCE.md)
        """
        self.logger = logger if logger else _setup_default_logger()

        if load_env_file:
            try:
                from dotenv import load_dotenv
            except ImportError:
                pass
            else:
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
        self.total_timeout = total_timeout
        self.retry_non_idempotent = retry_non_idempotent
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

        # --- circuit breaker (per host) ---
        if circuit_breaker is True:
            circuit_breaker = CircuitBreakerConfig()
        self.circuit_breaker_config: CircuitBreakerConfig | None = circuit_breaker or None
        self._breakers: dict[str, CircuitBreaker] = {}
        self._breakers_lock = threading.Lock()

        # --- rate limiting & shared state ---
        if key_rate_limit is not None:
            requests_count, per_seconds = key_rate_limit
            if requests_count < 1 or per_seconds <= 0:
                raise ValueError("key_rate_limit must be (requests >= 1, per_seconds > 0)")
            self._bucket_capacity = int(requests_count)
            self._bucket_refill = requests_count / float(per_seconds)
        self.key_rate_limit = key_rate_limit
        self.respect_rate_limit_headers = respect_rate_limit_headers
        self._state_shared = state_backend is not None and state_backend.shared
        if state_backend is None and key_rate_limit is not None:
            state_backend = InMemoryStateBackend(shared=False)
        self.state_backend = state_backend
        self.state_sync_interval = max(0.0, state_sync_interval)
        self._last_state_sync = float('-inf')
        self._key_ids: dict[str, str] = {}
        self._invalid_ids: set[str] = set()
        self._state_error_logged_at = 0.0

        # --- background key refresh ---
        self.auto_refresh_interval = auto_refresh_interval
        if auto_refresh_interval is not None and secret_provider is None:
            raise ValueError("auto_refresh_interval requires a secret_provider")

        self._log_initialization_summary()

    def _init_rotation_strategy(self, rotation_strategy: str | RotationStrategy | BaseRotationStrategy) -> None:
        if isinstance(rotation_strategy, BaseRotationStrategy):
            self.rotation_strategy = rotation_strategy
        else:
            strategy_name = (
                rotation_strategy.value if isinstance(rotation_strategy, RotationStrategy)
                else str(rotation_strategy).lower()
            )
            kwargs = dict(self.rotation_strategy_kwargs)
            keys: list[str] | dict[str, float] = self.key_manager.get_keys()

            if strategy_name == "weighted":
                # Weighted strategy needs {key: weight}; default to equal weights
                weights = kwargs.pop("weights", None) or {}
                keys = {k: float(weights.get(k, 1.0)) for k in keys}

            self.rotation_strategy = create_rotation_strategy(strategy_name, keys, **kwargs)
        # The rotator owns per-key metrics - strategies must not keep a second copy
        release = getattr(self.rotation_strategy, 'use_external_metrics', None)
        if release is not None:
            release()

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
    def keys(self) -> list[str]:
        return self.key_manager.get_keys()

    @keys.setter
    def keys(self, new_keys: list[str]):
        cleaned = parse_keys(list(new_keys), logger=self.logger)
        self.key_manager.reinit_keys(cleaned)
        if hasattr(self.rotation_strategy, 'update_keys'):
            self.rotation_strategy.update_keys(cleaned)
        kept = set(cleaned)
        self._key_ids = {k: v for k, v in self._key_ids.items() if k in kept}

    @property
    def _key_metrics(self) -> dict[str, KeyMetrics]:
        return self.key_manager.get_metric_objects()

    @property
    def key_count(self) -> int:
        return self.key_manager.get_key_count()

    def _remove_key(self, key: str) -> None:
        if self.key_manager.remove_key(key) and hasattr(self.rotation_strategy, 'update_keys'):
            self.rotation_strategy.update_keys(self.key_manager.get_keys())

    def _key_id(self, key: str) -> str:
        kid = self._key_ids.get(key)
        if kid is None:
            backend = self.state_backend
            kid = backend.key_id(key) if backend is not None else StateBackend().key_id(key)
            self._key_ids[key] = kid
        return kid

    def _filter_invalid(self, keys: list[str]) -> list[str]:
        if not self._invalid_ids:
            return keys
        return [k for k in keys if self._key_id(k) not in self._invalid_ids]

    async def refresh_keys_from_provider(self) -> list[str]:
        """
        Reloads keys from the configured secret provider.

        Metrics of keys that are still present are preserved. Keys rejected with
        401/403 earlier are not re-added. If the provider returns no keys, the
        current keys are kept.

        Returns:
            List[str]: The active key list after refresh
        """
        if self.secret_provider is None:
            raise ValueError("No secret_provider configured")
        new_keys = await self.secret_provider.refresh_keys()
        new_keys = self._filter_invalid(list(new_keys or []))
        if not new_keys:
            self.logger.warning("Secret provider returned no usable keys; keeping current keys")
            return self.keys
        if new_keys != self.keys:
            self.keys = new_keys
            self.logger.info(f"🔄 Keys refreshed from provider: {self.key_count} keys active")
        return self.keys

    def refresh_keys_from_provider_sync(self) -> list[str]:
        """Synchronous version of refresh_keys_from_provider()."""
        return _run_coroutine_sync(self.refresh_keys_from_provider)

    def get_metrics(self) -> dict:
        return self.metrics.get_metrics() if self.metrics else {}

    def get_key_statistics(self) -> dict:
        return self.key_manager.get_metrics()

    def get_circuit_states(self) -> dict[str, str]:
        """Circuit breaker state per host ('CLOSED' / 'OPEN' / 'HALF_OPEN')."""
        with self._breakers_lock:
            breakers = dict(self._breakers)
        return {host: b.get_state() for host, b in breakers.items()}

    def reset_key_health(self, key: str | None = None):
        self.key_manager.reset_health(key)

    def export_config(self) -> dict[str, Any]:
        config = {
            'keys_count': self.key_manager.get_key_count(),
            'max_retries': self.max_retries,
            'base_delay': self.base_delay,
            'max_delay': self.max_delay,
            'timeout': self.timeout,
            'total_timeout': self.total_timeout,
            'strategy': self.rotation_strategy.__class__.__name__,
            'metrics_enabled': self.metrics is not None,
            'circuit_breaker': self.circuit_breaker_config is not None,
            'key_rate_limit': self.key_rate_limit,
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
    # Shared state
    # ------------------------------------------------------------------

    def _log_state_error(self, action: str, error: Exception) -> None:
        # Shared state is best effort: a Redis outage must not break requests.
        now = time.monotonic()
        if now - self._state_error_logged_at > 30:
            self._state_error_logged_at = now
            self.logger.warning(f"State backend {action} failed (continuing locally): {error}")

    def _state_sync_due(self) -> bool:
        if not self._state_shared:
            return False
        now = time.monotonic()
        if now - self._last_state_sync < self.state_sync_interval:
            return False
        self._last_state_sync = now
        return True

    def _apply_snapshot(self, snapshot: SharedState) -> None:
        if not snapshot.rate_limited and not snapshot.invalid:
            return
        by_id = {self._key_id(k): k for k in self.key_manager.get_keys()}
        for kid, until in snapshot.rate_limited.items():
            key = by_id.get(kid)
            if key is not None:
                self.key_manager.mark_rate_limited(key, until)
        for kid in snapshot.invalid:
            self._invalid_ids.add(kid)
            key = by_id.get(kid)
            if key is not None:
                self.logger.warning(f"❌ Key {_mask_key(key)} was invalidated by another instance")
                self._remove_key(key)

    def _flush_reports(self, ctx: _RequestContext) -> None:
        if not ctx.reports:
            return
        backend = self.state_backend
        reports, ctx.reports = ctx.reports, []
        if backend is None:
            return
        for method, args in reports:
            try:
                getattr(backend, method)(*args)
            except Exception as e:
                self._log_state_error(method, e)

    def _mark_rate_limited(self, ctx: _RequestContext, key: str, until: float) -> None:
        self.key_manager.mark_rate_limited(key, until)
        if self._state_shared:
            ctx.reports.append(("report_rate_limited", (self._key_id(key), until)))

    # ------------------------------------------------------------------
    # Circuit breaker
    # ------------------------------------------------------------------

    def _breaker_for(self, url: str) -> CircuitBreaker | None:
        config = self.circuit_breaker_config
        if config is None:
            return None
        host = _host_of(url)
        breaker = self._breakers.get(host)
        if breaker is None:
            with self._breakers_lock:
                breaker = self._breakers.get(host)
                if breaker is None:
                    breaker = self._breakers[host] = CircuitBreaker.from_config(config, name=host)
        return breaker

    def _check_breaker(self, ctx: _RequestContext) -> None:
        breaker = ctx.breaker
        if breaker is None:
            return
        if breaker.allow_request():
            ctx.breaker_pending = True
        else:
            raise CircuitOpenError(
                _host_of(ctx.url), breaker.retry_after(),
                last_response=ctx.last_response, last_exception=ctx.last_exception,
            )

    # ------------------------------------------------------------------
    # Request preparation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_url(url: str) -> None:
        if not url or not url.strip():
            raise ValueError("URL cannot be empty")

    @staticmethod
    def _get_domain_from_url(url: str) -> str:
        return _host_of(url) if url else ""

    @staticmethod
    def _endpoint_label(url: str) -> str:
        return _endpoint_label(url)

    def _new_context(self, method: str, url: str, kwargs: dict[str, Any]) -> _RequestContext:
        total_timeout = kwargs.pop("total_timeout", self.total_timeout)
        deadline = time.monotonic() + total_timeout if total_timeout is not None else None
        method_upper = method.upper()
        idempotent = (
            self.retry_non_idempotent
            or method_upper in IDEMPOTENT_METHODS
            or get_header(kwargs.get("headers"), "Idempotency-Key") is not None
        )
        return _RequestContext(method, url, idempotent, deadline, self._breaker_for(url))

    def _infer_auth_header(self, key: str) -> tuple[str, str]:
        for prefix in API_KEY_PATTERNS['bearer']:
            if key.startswith(prefix):
                return DEFAULT_AUTH_HEADERS['bearer'], f"Bearer {key}"
        if len(key) == API_KEY_PATTERNS['api_key']:
            return DEFAULT_AUTH_HEADERS['api_key'], key
        return DEFAULT_AUTH_HEADERS['bearer'], f"Key {key}"

    def get_next_key(self) -> str:
        metrics_objects = self.key_manager.get_metrics_view()
        if not metrics_objects:
            raise AllKeysExhaustedError("No valid keys available")
        try:
            key = self.rotation_strategy.get_next_key(metrics_objects)
        except ValueError as e:
            raise AllKeysExhaustedError(f"No valid keys available: {e}") from e

        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug("Selected key: %s", _mask_key(key))
        return key

    def get_next_user_agent(self) -> str | None:
        if not self.user_agents:
            return None
        with self._cycle_lock:
            ua = self.user_agents[self._ua_index % len(self.user_agents)]
            self._ua_index = (self._ua_index + 1) % len(self.user_agents)
        return ua

    def get_next_proxy(self) -> str | None:
        if not self.proxy_list:
            return None
        with self._cycle_lock:
            proxy = self.proxy_list[self._proxy_index % len(self.proxy_list)]
            self._proxy_index = (self._proxy_index + 1) % len(self.proxy_list)
        return proxy

    def _prepare_headers_and_cookies(
            self, key: str, custom_headers: dict[str, str] | None, url: str
    ) -> tuple[dict[str, str], dict[str, str]]:
        headers = dict(custom_headers) if custom_headers else {}
        cookies: dict[str, str] = {}

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

        present = {h.lower() for h in headers} if headers else ()
        # Add the inferred auth header only if the request/callback set no auth header
        # itself - otherwise the key would be sent twice (e.g. X-API-Key + Authorization).
        if "authorization" not in present and "x-api-key" not in present:
            header_name, header_value = self._infer_auth_header(key)
            headers[header_name] = header_value

        if self.user_agents and "user-agent" not in present:
            user_agent = self.get_next_user_agent()
            if user_agent:
                headers["User-Agent"] = user_agent

        return headers, cookies

    def _prepare_request(
            self, method: str, url: str, key: str, kwargs: dict[str, Any], attempt: int
    ) -> tuple[dict[str, Any], RequestInfo | None]:
        headers, cookies = self._prepare_headers_and_cookies(key, kwargs.get("headers"), url)

        request_kwargs = dict(kwargs)
        request_kwargs["headers"] = headers
        user_cookies = kwargs.get("cookies")
        if isinstance(user_cookies, dict):
            cookies = {**user_cookies, **cookies}
        request_kwargs["cookies"] = cookies

        request_info = None
        if self.middlewares:
            request_info = RequestInfo(
                method=method, url=url, headers=headers, cookies=cookies,
                key=key, attempt=attempt, kwargs=request_kwargs
            )
        return request_kwargs, request_info

    def _attempt_timeout(self, kwargs: dict[str, Any], ctx: _RequestContext) -> float | None:
        """Per-attempt timeout: the user's (or default) timeout, clipped to the remaining deadline."""
        user_timeout = kwargs.get("timeout")
        if user_timeout is None:
            timeout = self.timeout
        elif isinstance(user_timeout, (int, float)):
            timeout = float(user_timeout)
        else:
            return None  # library-specific timeout object - passed through as is
        remaining = ctx.remaining()
        if remaining is not None:
            timeout = min(timeout, max(remaining, 0.001))
        return timeout

    # ------------------------------------------------------------------
    # Delays
    # ------------------------------------------------------------------

    def _random_delay_value(self) -> float:
        if not self.random_delay_range:
            return 0.0
        delay = random.uniform(self.random_delay_range[0], self.random_delay_range[1])
        return delay + random.uniform(0, delay * 0.1)

    def _calculate_backoff_delay(self, attempt: int) -> float:
        # Cap the exponent too, to avoid float overflow for huge max_retries
        delay = min(self.base_delay * (2 ** min(attempt, 30)), self.max_delay)
        return min(delay + random.uniform(0, delay * 0.1), self.max_delay)

    def _recovery_timeout(self) -> float | None:
        return getattr(self.rotation_strategy, 'recovery_timeout', None)

    def _has_available_key(self) -> bool:
        now = time.time()
        recovery_timeout = self._recovery_timeout()
        return any(
            m.is_available(now, recovery_timeout)
            for m in self.key_manager.get_metrics_view().values()
        )

    def _time_until_key_available(self) -> float | None:
        """Seconds until the earliest rate-limited key becomes usable again (None if unknown)."""
        now = time.time()
        waits = [
            m.rate_limit_reset - now
            for m in self.key_manager.get_metrics_view().values()
            if m.rate_limit_reset > now
        ]
        return min(waits) if waits else None

    def _retry_delay(self, attempt: int, error_type: ErrorType | None, headers: Any) -> float:
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

    def _check_deadline(self, ctx: _RequestContext, delay: float = 0.0) -> None:
        """Raises DeadlineExceededError if the budget is spent (or would be by waiting `delay`)."""
        remaining = ctx.remaining()
        if remaining is not None and (remaining <= 0 or delay >= remaining):
            raise DeadlineExceededError(
                f"Request deadline exceeded after {ctx.attempt} attempt(s)",
                last_response=ctx.last_response, last_exception=ctx.last_exception,
            )

    def _check_budget(self, ctx: _RequestContext) -> None:
        if ctx.attempt >= self.max_retries:
            raise self._exhausted_error(ctx.last_response, ctx.last_exception)
        if self.key_count == 0:
            raise AllKeysExhaustedError(
                "All keys are invalid (empty list)",
                last_response=ctx.last_response, last_exception=ctx.last_exception,
            )
        self._check_deadline(ctx)

    # ------------------------------------------------------------------
    # Token bucket (client-side rate limit)
    # ------------------------------------------------------------------

    def _bucket_wait(self, key: str) -> float:
        """Takes a token for `key` from the backend; returns seconds to wait (0 = acquired)."""
        try:
            return self.state_backend.acquire_token(
                self._key_id(key), self._bucket_capacity, self._bucket_refill
            )
        except Exception as e:
            self._log_state_error("acquire_token", e)
            return 0.0  # fail open

    def _after_bucket_denied(self, ctx: _RequestContext, key: str, wait: float) -> float:
        """Marks `key` as limited locally; returns how long to sleep before selecting again (0 = retry now)."""
        self.key_manager.mark_rate_limited(key, time.time() + wait)
        if self._has_available_key():
            return 0.0
        until_free = self._time_until_key_available()
        return min(until_free if until_free is not None else wait, self.max_delay)

    # ------------------------------------------------------------------
    # Response handling (shared by sync/async)
    # ------------------------------------------------------------------

    def _record(
            self, key: str, endpoint: str, success: bool, request_time: float,
            is_rate_limited: bool = False, key_success: bool | None = None
    ) -> None:
        if self.metrics:
            self.metrics.record_request(
                key=key, endpoint=endpoint, success=success,
                response_time=request_time, is_rate_limited=is_rate_limited
            )
        self.key_manager.update_metrics(
            key, success if key_success is None else key_success, request_time, is_rate_limited
        )

    def _apply_rate_limit_headers(self, ctx: _RequestContext, key: str, headers: Any) -> None:
        """Proactive limiting: `Remaining: 0` means the next request with this key would get 429."""
        remaining, reset = parse_rate_limit_headers(headers)
        if remaining is not None and remaining <= 0 and reset is not None and reset > time.time():
            self._mark_rate_limited(ctx, key, reset)

    def _handle_response(
            self,
            ctx: _RequestContext,
            key: str,
            status_code: int,
            headers: Any,
            classifier_response: Any,
            callback_arg: Any,
            request_time: float,
    ) -> tuple[_Action, ErrorType | None]:
        endpoint = ctx.endpoint
        error_type = self.error_classifier.classify_error(response=classifier_response)

        # Host health: 5xx = failure, anything else (incl. 4xx/429) = host is alive
        ctx.breaker_verdict(status_code < 500)

        if error_type == ErrorType.PERMANENT:
            if self.error_classifier.should_remove_key(classifier_response):
                self._record(key, endpoint, False, request_time)
                self.logger.error(
                    f"❌ Key {_mask_key(key)} permanently invalid (Status: {status_code}). Removing it from rotation.")
                kid = self._key_id(key)
                self._invalid_ids.add(kid)
                if self._state_shared:
                    ctx.reports.append(("report_invalid", (kid,)))
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
                    _, reset = parse_rate_limit_headers(headers)
                    if reset is not None:
                        retry_after = max(0.0, reset - time.time())
                if retry_after is None:
                    retry_after = self._calculate_backoff_delay(ctx.attempt)
                self._mark_rate_limited(ctx, key, time.time() + retry_after)
            if not ctx.idempotent and status_code not in NON_IDEMPOTENT_RETRYABLE_STATUSES:
                # The server may already have processed this POST/PATCH - retrying could
                # duplicate the operation. Hand the response to the caller instead.
                self.logger.warning(
                    f"⚠️ {ctx.method} got {status_code}; not retrying a non-idempotent request "
                    f"(pass retry_non_idempotent=True or an Idempotency-Key header to allow it)")
                return _Action.RETURN, error_type
            msg = "Rate limited" if is_rate_limited else "Temporary error"
            self.logger.warning(
                f"↻ {msg} (Status: {status_code}, key: {_mask_key(key)}). "
                f"Attempt {ctx.attempt + 1}/{self.max_retries}")
            return _Action.RETRY, error_type

        if self.should_retry_callback and self.should_retry_callback(callback_arg):
            self._record(key, endpoint, False, request_time)
            self.logger.warning(
                f"↻ Retry requested by should_retry_callback (Status: {status_code}). "
                f"Attempt {ctx.attempt + 1}/{self.max_retries}")
            return _Action.RETRY, None

        self._record(key, endpoint, True, request_time)
        if self.respect_rate_limit_headers:
            self._apply_rate_limit_headers(ctx, key, headers)
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug("✅ Success (Status: %s)", status_code)
        return _Action.RETURN, None

    def _handle_network_error(self, ctx: _RequestContext, key: str, error: BaseException,
                              request_time: float, safe_to_retry: bool) -> bool:
        """Records a network failure. Returns True if the request may be retried."""
        ctx.last_exception = error
        self._record(key, ctx.endpoint, False, request_time)
        ctx.breaker_verdict(False)
        if not ctx.idempotent and not safe_to_retry:
            self.logger.warning(
                f"⚠️ {ctx.method} failed with {type(error).__name__} after the request may have "
                f"been sent; not retrying a non-idempotent request")
            return False
        ctx.attempt += 1
        self.logger.warning(
            f"⚠️ Network error: {type(error).__name__}: {error}. Attempt {ctx.attempt}/{self.max_retries}")
        return True

    def _exhausted_error(self, last_response: Any, last_exception: BaseException | None) -> AllKeysExhaustedError:
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

def _auto_refresh_loop(rotator_ref: weakref.ref, interval: float, stop: threading.Event) -> None:
    # Holds only a weak reference, so an unused rotator can still be garbage-collected
    while not stop.wait(interval):
        rotator = rotator_ref()
        if rotator is None:
            return
        try:
            rotator.refresh_keys_from_provider_sync()
        except Exception as e:
            rotator.logger.warning(f"Background key refresh failed: {e}")
        del rotator


class APIKeyRotator(BaseKeyRotator):
    """
    Synchronous rotator.

    Args (in addition to BaseKeyRotator):
        http_backend: 'requests' (default) or 'httpx'.
        http2: Enable HTTP/2 (httpx backend only).
        http_client_kwargs: Extra settings for the HTTP client (e.g. verify, cert).
    """

    def __init__(self, *args, http_backend: str = "requests", http2: bool = False,
                 http_client_kwargs: dict[str, Any] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._transport: SyncTransport = create_sync_transport(
            http_backend, self.pool_size, http2, http_client_kwargs
        )
        self.http_backend = self._transport.name
        self._refresh_stop: threading.Event | None = None
        self._refresh_thread: threading.Thread | None = None
        if self.auto_refresh_interval is not None:
            self.start_auto_refresh(self.auto_refresh_interval)
        self.logger.info(f"✅ Sync rotator initialized ({self.http_backend} backend, connection pooling)")

    @property
    def session(self) -> Any:
        """The underlying HTTP client (requests.Session or httpx.Client)."""
        return self._transport.session

    def start_auto_refresh(self, interval: float) -> None:
        """Reloads keys from the secret provider every `interval` seconds on a daemon thread."""
        if self.secret_provider is None:
            raise ValueError("Auto refresh requires a secret_provider")
        self.stop_auto_refresh()
        stop = threading.Event()
        thread = threading.Thread(
            target=_auto_refresh_loop, args=(weakref.ref(self), interval, stop),
            name="apikeyrotator-refresh", daemon=True,
        )
        self._refresh_stop, self._refresh_thread = stop, thread
        self.auto_refresh_interval = interval
        thread.start()

    def stop_auto_refresh(self) -> None:
        if self._refresh_stop is not None:
            self._refresh_stop.set()
            if self._refresh_thread is not None and self._refresh_thread is not threading.current_thread():
                self._refresh_thread.join(timeout=5)
        self._refresh_stop = self._refresh_thread = None

    def close(self) -> None:
        """Stops background refresh and closes the HTTP client and its connection pool."""
        self.stop_auto_refresh()
        self._transport.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        stop = getattr(self, '_refresh_stop', None)
        if stop is not None:
            stop.set()

    # --- middleware helpers ---

    def _run_before_request(self, request_info: RequestInfo, request_kwargs: dict[str, Any]) -> ResponseInfo | None:
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

    # --- helpers ---

    def _sleep(self, ctx: _RequestContext, delay: float) -> None:
        if delay > 0:
            self._check_deadline(ctx, delay)
            time.sleep(delay)

    def _sync_state(self) -> None:
        if self._state_sync_due():
            try:
                snapshot = self.state_backend.snapshot()
            except Exception as e:
                self._log_state_error("snapshot", e)
                return
            self._apply_snapshot(snapshot)

    def _acquire_key(self, ctx: _RequestContext) -> str:
        while True:
            key = self.get_next_key()
            if self.key_rate_limit is None:
                return key
            wait = self._bucket_wait(key)
            if wait <= 0:
                return key
            self._sleep(ctx, self._after_bucket_denied(ctx, key, wait))
            if self.key_count == 0:
                raise AllKeysExhaustedError("All keys are invalid (empty list)")

    # --- request ---

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        self._validate_url(url)
        ctx = self._new_context(method, url, kwargs)
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug("Initiating %s request to %s", method, url)
        stream = bool(kwargs.get("stream"))
        transport = self._transport
        middlewares = self.middlewares
        self._sync_state()

        try:
            while True:
                self._check_budget(ctx)
                self._check_breaker(ctx)

                key = self._acquire_key(ctx)
                request_kwargs, request_info = self._prepare_request(method, url, key, kwargs, ctx.attempt)

                if middlewares:
                    short_circuit = self._run_before_request(request_info, request_kwargs)
                    if short_circuit is not None:
                        ctx.release_breaker()
                        return _build_sync_response(short_circuit, url, transport.name)

                if self.random_delay_range:
                    self._sleep(ctx, self._random_delay_value())

                timeout = self._attempt_timeout(kwargs, ctx)
                start_time = time.monotonic()
                try:
                    response = transport.request(method, url, request_kwargs, self.get_next_proxy(), timeout)
                except transport.network_errors as e:
                    request_time = time.monotonic() - start_time
                    if middlewares:
                        self._run_on_error(ErrorInfo(exception=e, request_info=request_info))
                    if not self._handle_network_error(ctx, key, e, request_time,
                                                      transport.is_safe_to_retry_error(e)):
                        raise
                    if ctx.attempt < self.max_retries:
                        self._sleep(ctx, self._calculate_backoff_delay(ctx.attempt - 1))
                    continue

                request_time = time.monotonic() - start_time
                status = response.status_code
                headers = response.headers

                response_info = None
                if middlewares:
                    response_info = ResponseInfo(
                        status_code=status, headers=dict(headers),
                        content=None if stream else response.content,
                        request_info=request_info, response_time=request_time,
                    )
                    self._run_after_request(response_info)

                action, error_type = self._handle_response(
                    ctx, key, status, headers,
                    classifier_response=response, callback_arg=response,
                    request_time=request_time,
                )

                if action is _Action.RETURN:
                    if ctx.last_response is not None:
                        transport.close_response(ctx.last_response)
                    return response

                if response_info is not None:
                    self._run_on_error(ErrorInfo(
                        exception=HTTPStatusError(status),
                        request_info=request_info, response_info=response_info,
                    ))

                # Release the previous failed response's connection before keeping this one
                if ctx.last_response is not None:
                    transport.close_response(ctx.last_response)
                ctx.last_response = response
                ctx.last_exception = None

                if action is _Action.SWITCH:
                    self._flush_reports(ctx)
                    continue

                ctx.attempt += 1
                self._flush_reports(ctx)
                if ctx.attempt < self.max_retries:
                    self._sleep(ctx, self._retry_delay(ctx.attempt - 1, error_type, headers))
        finally:
            ctx.release_breaker()
            self._flush_reports(ctx)

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
    if hasattr(value, "__await__"):
        return await value
    return value


class AsyncAPIKeyRotator(BaseKeyRotator):
    """
    Asynchronous rotator.

    Args (in addition to BaseKeyRotator):
        http_backend: 'aiohttp' (default) or 'httpx'.
        http2: Enable HTTP/2 (httpx backend only).
        http_client_kwargs: Extra settings for the HTTP client session.
    """

    def __init__(self, *args, http_backend: str = "aiohttp", http2: bool = False,
                 http_client_kwargs: dict[str, Any] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._transport: AsyncTransport = create_async_transport(
            http_backend, self.pool_size, self.timeout, http2, http_client_kwargs
        )
        self.http_backend = self._transport.name
        self._refresh_task: asyncio.Task | None = None
        self.logger.info(f"✅ Async rotator initialized ({self.http_backend} backend)")

    @property
    def _session(self) -> Any:
        """The underlying client session (aiohttp.ClientSession / httpx.AsyncClient) or None."""
        return self._transport.session

    @_session.setter
    def _session(self, value: Any) -> None:
        self._transport.session = value

    async def __aenter__(self):
        await self._get_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self) -> None:
        """Stops background refresh and closes the underlying client session."""
        await self.stop_auto_refresh()
        await self._transport.close()

    async def _get_session(self) -> Any:
        self._ensure_background_tasks()
        return await self._transport.open()

    def _ensure_background_tasks(self) -> None:
        if self.auto_refresh_interval is not None and self._refresh_task is None:
            self.start_auto_refresh(self.auto_refresh_interval)

    def start_auto_refresh(self, interval: float) -> None:
        """Reloads keys from the secret provider every `interval` seconds (needs a running event loop)."""
        if self.secret_provider is None:
            raise ValueError("Auto refresh requires a secret_provider")
        self.auto_refresh_interval = interval
        if self._refresh_task is not None and not self._refresh_task.done():
            self._refresh_task.cancel()
        self._refresh_task = asyncio.get_running_loop().create_task(
            self._auto_refresh_loop(weakref.ref(self), interval), name="apikeyrotator-refresh"
        )

    @staticmethod
    async def _auto_refresh_loop(rotator_ref: weakref.ref, interval: float) -> None:
        while True:
            await asyncio.sleep(interval)
            rotator = rotator_ref()
            if rotator is None:
                return
            try:
                await rotator.refresh_keys_from_provider()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                rotator.logger.warning(f"Background key refresh failed: {e}")
            del rotator

    async def stop_auto_refresh(self) -> None:
        task, self._refresh_task = self._refresh_task, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    async def _release(self, response: Any) -> None:
        await self._transport.release(response)

    # --- middleware helpers ---

    async def _run_before_request(
            self, request_info: RequestInfo, request_kwargs: dict[str, Any]
    ) -> ResponseInfo | None:
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

    # --- helpers ---

    async def _sleep(self, ctx: _RequestContext, delay: float) -> None:
        if delay > 0:
            self._check_deadline(ctx, delay)
            await asyncio.sleep(delay)

    async def _backend_call(self, fn: Callable, *args) -> Any:
        """Runs a state backend call; blocking backends (Redis) run in a worker thread."""
        if self.state_backend is not None and self.state_backend.blocking:
            return await asyncio.to_thread(fn, *args)
        return fn(*args)

    async def _sync_state(self) -> None:
        if self._state_sync_due():
            try:
                snapshot = await self._backend_call(self.state_backend.snapshot)
            except Exception as e:
                self._log_state_error("snapshot", e)
                return
            self._apply_snapshot(snapshot)

    async def _flush_reports_async(self, ctx: _RequestContext) -> None:
        if not ctx.reports:
            return
        if self.state_backend is not None and self.state_backend.blocking:
            reports, ctx.reports = ctx.reports, []
            holder = _RequestContext(ctx.method, ctx.url, ctx.idempotent, None, None)
            holder.reports = reports
            await asyncio.to_thread(self._flush_reports, holder)
        else:
            self._flush_reports(ctx)

    async def _acquire_key(self, ctx: _RequestContext) -> str:
        while True:
            key = self.get_next_key()
            if self.key_rate_limit is None:
                return key
            wait = await self._backend_call(self._bucket_wait, key)
            if wait <= 0:
                return key
            await self._sleep(ctx, self._after_bucket_denied(ctx, key, wait))
            if self.key_count == 0:
                raise AllKeysExhaustedError("All keys are invalid (empty list)")

    # --- request ---

    async def request(self, method: str, url: str, **kwargs) -> aiohttp.ClientResponse:
        self._validate_url(url)
        ctx = self._new_context(method, url, kwargs)
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug("Initiating async %s request to %s", method, url)
        self._ensure_background_tasks()
        transport = self._transport
        middlewares = self.middlewares
        await self._sync_state()

        try:
            while True:
                self._check_budget(ctx)
                self._check_breaker(ctx)

                key = await self._acquire_key(ctx)
                request_kwargs, request_info = self._prepare_request(method, url, key, kwargs, ctx.attempt)

                if middlewares:
                    short_circuit = await self._run_before_request(request_info, request_kwargs)
                    if short_circuit is not None:
                        ctx.release_breaker()
                        return _CachedAsyncResponse(
                            short_circuit.status_code, short_circuit.headers, short_circuit.content, url
                        )

                if self.random_delay_range:
                    await self._sleep(ctx, self._random_delay_value())

                # The session already carries the default timeout - only pass one when it differs
                timeout = (
                    self._attempt_timeout(kwargs, ctx)
                    if ctx.deadline is not None or kwargs.get("timeout") is not None else None
                )
                start_time = time.monotonic()
                try:
                    response = await transport.request(method, url, request_kwargs, self.get_next_proxy(), timeout)
                    request_time = time.monotonic() - start_time
                    status = transport.status(response)
                    headers = response.headers

                    response_info = None
                    if middlewares:
                        # Read the body so middlewares (e.g. caching) can see it; the client
                        # caches it, so the caller can still read()/json() it.
                        content = await transport.read(response)
                        response_info = ResponseInfo(
                            status_code=status, headers=dict(headers),
                            content=content, request_info=request_info, response_time=request_time,
                        )
                        await self._run_after_request(response_info)
                except transport.network_errors as e:
                    request_time = time.monotonic() - start_time
                    if middlewares:
                        await self._run_on_error(ErrorInfo(exception=e, request_info=request_info))
                    if not self._handle_network_error(ctx, key, e, request_time,
                                                      transport.is_safe_to_retry_error(e)):
                        raise
                    if ctx.attempt < self.max_retries:
                        await self._sleep(ctx, self._calculate_backoff_delay(ctx.attempt - 1))
                    continue

                action, error_type = self._handle_response(
                    ctx, key, status, headers,
                    classifier_response=_ResponseCodeWrapper(status, headers),
                    callback_arg=status,
                    request_time=request_time,
                )

                if action is _Action.RETURN:
                    return response

                if response_info is not None:
                    await self._run_on_error(ErrorInfo(
                        exception=HTTPStatusError(status),
                        request_info=request_info, response_info=response_info,
                    ))

                # Failed responses are released immediately so the connection returns
                # to the pool; the last one is still exposed via AllKeysExhaustedError.
                await self._release(response)
                ctx.last_response = response
                ctx.last_exception = None

                if action is _Action.SWITCH:
                    await self._flush_reports_async(ctx)
                    continue

                ctx.attempt += 1
                await self._flush_reports_async(ctx)
                if ctx.attempt < self.max_retries:
                    await self._sleep(ctx, self._retry_delay(ctx.attempt - 1, error_type, headers))
        finally:
            ctx.release_breaker()
            if ctx.reports:
                await self._flush_reports_async(ctx)

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
