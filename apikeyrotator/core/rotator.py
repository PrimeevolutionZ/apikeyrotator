"""
Public rotators.

The rotators are facades: they assemble the components (see RequestEngine for the
list) from the constructor arguments, expose the public API and drive the shared
request loop - ``APIKeyRotator`` with blocking I/O, ``AsyncAPIKeyRotator`` with
asyncio. All request decisions live in ``engine.py``.
"""

from __future__ import annotations
import asyncio
import logging
import threading
import time
import weakref
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from apikeyrotator.metrics import RotatorMetrics
from apikeyrotator.middleware import RotatorMiddleware
from apikeyrotator.providers import SecretProvider
from apikeyrotator.state import InMemoryStateBackend, StateBackend
from apikeyrotator.strategies import BaseRotationStrategy, KeyMetrics, RotationStrategy
from apikeyrotator.utils import CircuitBreakerConfig, ErrorClassifier

from .breakers import BreakerRegistry
from .config import (
    HTTPConfig,
    RateLimitConfig,
    RequestConfig,
    RetryConfig,
    SharedStateConfig,
    merge_config,
)
from .config_loader import ConfigLoader
from .engine import (
    AFTER,
    BEFORE,
    CALL,
    DONE,
    ON_ERROR,
    READ,
    RELEASE,
    SEND,
    SHORT,
    SLEEP,
    Flow,
    NetworkFailure,
    RequestEngine,
)
from .key_parser import parse_keys
from .keys import KeyPool
from .limits import RateLimiter
from .middleware_chain import MiddlewareChain
from .policy import (  # noqa: F401 - re-exported for backwards compatibility
    DEFAULT_MAX_DELAY,
    IDEMPOTENT_METHODS,
    NON_IDEMPOTENT_RETRYABLE_STATUSES,
    RetryPolicy,
)
from .request_builder import (  # noqa: F401 - re-exported for backwards compatibility
    API_KEY_PATTERNS,
    DEFAULT_AUTH_HEADERS,
    RequestBuilder,
    infer_auth_header,
)
from .responses import UnifiedResponse, build_async_response, build_sync_response
from .shared_state import StateSync
from .transport import (
    AsyncTransport,
    SyncTransport,
    create_async_transport,
    create_sync_transport,
)
from .util import host_of, in_running_loop, mask_key, run_coroutine_sync, unique_labels


if TYPE_CHECKING:  # HTTP libraries are imported lazily by the transports
    import aiohttp
    import requests

DEFAULT_POOL_SIZE = 100


class _Delegate:
    """Attribute of the rotator stored on one of its components (so updates reach it)."""
    __slots__ = ('component', 'attr')

    def __init__(self, component: str, attr: str | None = None):
        self.component = component
        self.attr = attr or ""   # "" = same name as the rotator attribute (set in __set_name__)

    def __set_name__(self, owner: type, name: str) -> None:
        if not self.attr:
            self.attr = name

    def __get__(self, obj: Any, objtype: type | None = None) -> Any:
        if obj is None:
            return self
        return getattr(getattr(obj, self.component), self.attr)

    def __set__(self, obj: Any, value: Any) -> None:
        setattr(getattr(obj, self.component), self.attr, value)


# ============================================================================
# BASE ROTATOR
# ============================================================================

class BaseKeyRotator:
    """
    Shared configuration and public API of both rotators.

    Constructor arguments are grouped by the component they configure. Groups marked
    with a config class can also be passed as one object (``retry=RetryConfig(...)``,
    see ``apikeyrotator.core.config``):

    - keys: ``api_keys``, ``env_var``, ``load_env_file``, ``secret_provider``,
      ``auto_refresh_interval``, ``rotation_strategy``, ``rotation_strategy_kwargs``,
      ``recovery_timeout``
    - retries & time (RetryPolicy, ``retry=RetryConfig``): ``max_retries``, ``base_delay``, ``max_delay``,
      ``timeout``, ``total_timeout``, ``retry_non_idempotent``,
      ``should_retry_callback``, ``auto_idempotency_key``
    - limits (RateLimiter, ``rate_limits=RateLimitConfig``): ``key_rate_limit``,
      ``respect_rate_limit_headers``; ``circuit_breaker=CircuitBreakerConfig``
    - shared state (StateSync, ``shared_state=SharedStateConfig``): ``state_backend``,
      ``state_sync_interval``
    - request building (RequestBuilder, ``request=RequestConfig``): ``auth``,
      ``header_callback``, ``user_agents``, ``proxy_list``, ``random_delay_range``;
      ``config_file``, ``config_loader``, ``save_sensitive_headers``
    - observability & extensions: ``middlewares``, ``enable_metrics``,
      ``error_classifier``, ``logger``
    - HTTP client (``http=HTTPConfig``): ``pool_size``, ``http_backend``, ``http2``,
      ``http_client_kwargs`` (the last three in the subclasses); ``unified_response``

    See docs/API_REFERENCE.md for every argument.
    """

    # Public attributes live on the components; these keep them readable and writable.
    max_retries = _Delegate('_policy')
    base_delay = _Delegate('_policy')
    max_delay = _Delegate('_policy')
    timeout = _Delegate('_policy')
    total_timeout = _Delegate('_policy')
    retry_non_idempotent = _Delegate('_policy')
    should_retry_callback = _Delegate('_policy')
    random_delay_range = _Delegate('_policy')
    auto_idempotency_key = _Delegate('_policy')
    user_agents = _Delegate('_builder')
    proxy_list = _Delegate('_builder')
    save_sensitive_headers = _Delegate('_builder')
    config = _Delegate('_builder')
    key_rate_limit = _Delegate('_limiter')
    respect_rate_limit_headers = _Delegate('_limiter', 'respect_headers')
    circuit_breaker_config = _Delegate('_breakers', 'config')
    state_backend = _Delegate('_state', 'backend')
    state_sync_interval = _Delegate('_state', 'sync_interval')
    middlewares = _Delegate('_chain', 'middlewares')
    metrics = _Delegate('_engine', 'metrics')
    unified_response = _Delegate('_engine', 'unified')
    error_classifier = _Delegate('_engine', 'classifier')

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
            config_file: str | None = None,
            load_env_file: bool = False,
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
            auth: str | tuple[str, str] | bool | None = None,
            unified_response: bool = False,
            auto_idempotency_key: bool | str = False,
            *,
            retry: RetryConfig | None = None,
            rate_limits: RateLimitConfig | None = None,
            shared_state: SharedStateConfig | None = None,
            request: RequestConfig | None = None,
    ):
        self._logger = logger if logger else logging.getLogger(__name__)

        # Grouped settings (retry=RetryConfig(...) etc.) or their flat arguments
        r = merge_config("retry", retry, {
            "max_retries": max_retries, "base_delay": base_delay, "max_delay": max_delay,
            "timeout": timeout, "total_timeout": total_timeout,
            "retry_non_idempotent": retry_non_idempotent, "auto_idempotency_key": auto_idempotency_key,
            "should_retry_callback": should_retry_callback,
        })
        lim = merge_config("rate_limits", rate_limits, {
            "key_rate_limit": key_rate_limit, "respect_rate_limit_headers": respect_rate_limit_headers,
        })
        st = merge_config("shared_state", shared_state, {
            "state_backend": state_backend, "state_sync_interval": state_sync_interval,
        })
        req = merge_config("request", request, {
            "auth": auth, "header_callback": header_callback, "user_agents": user_agents,
            "proxy_list": proxy_list, "random_delay_range": random_delay_range,
        })
        state_backend, key_rate_limit = st["state_backend"], lim["key_rate_limit"]

        if load_env_file:
            try:
                from dotenv import find_dotenv, load_dotenv
            except ImportError:
                self._logger.warning("load_env_file=True but python-dotenv is not installed")
            else:
                # Search from the working directory: plain load_dotenv() searches from this
                # file's location, which never finds the application's .env once installed
                load_dotenv(find_dotenv(usecwd=True))

        self._policy = RetryPolicy(**r, random_delay_range=req["random_delay_range"])

        # --- keys ---
        self.secret_provider = secret_provider
        self._env_var = env_var
        if auto_refresh_interval is not None and secret_provider is None:
            raise ValueError("auto_refresh_interval requires a secret_provider")
        self.auto_refresh_interval = auto_refresh_interval
        #: True while keys still have to be loaded from the secret provider (async rotators
        #: created inside a running event loop load them on first use, in that loop)
        self._keys_pending = False
        keys: list[str] = []
        if api_keys is None and secret_provider is not None and self._defer_provider_keys():
            self._keys_pending = True
        else:
            if api_keys is None and secret_provider is not None:
                provider_keys = run_coroutine_sync(secret_provider.get_keys)
                if provider_keys:
                    api_keys = list(provider_keys)
                else:
                    self._logger.warning("Secret provider returned no keys, falling back to environment variable")
            keys = parse_keys(api_keys, env_var, self._logger)
            if not keys:
                raise ValueError("At least one API key is required")

        self.rotation_strategy_kwargs = rotation_strategy_kwargs or {}
        self._pool = KeyPool(keys, rotation_strategy, self.rotation_strategy_kwargs, self._logger,
                             recovery_timeout=recovery_timeout)

        # --- limits & shared state ---
        if state_backend is None and key_rate_limit is not None:
            state_backend = InMemoryStateBackend(shared=False)
        self._state = StateSync(state_backend, st["state_sync_interval"], self._pool, self._logger,
                                on_invalid=self._pool.remove)
        self._limiter = RateLimiter(self._pool, self._state, self._policy, key_rate_limit,
                                    lim["respect_rate_limit_headers"])
        self._breakers = BreakerRegistry(circuit_breaker)

        # --- request building ---
        self.config_file = config_file
        # A config file is read only when one is given (nothing is read from the CWD implicitly)
        if config_loader is None and config_file:
            config_loader = ConfigLoader(config_file=config_file, logger=self._logger)
        self.config_loader = config_loader
        self._builder = RequestBuilder(
            header_callback=req["header_callback"], user_agents=req["user_agents"],
            proxy_list=req["proxy_list"], save_sensitive_headers=save_sensitive_headers,
            config=config_loader.load_config() if config_loader is not None else {},
            auth=req["auth"],
        )

        self._chain = MiddlewareChain(middlewares, self._logger)
        self.enable_metrics = enable_metrics
        self.pool_size = max(1, int(pool_size))

        self._engine = RequestEngine(
            pool=self._pool, policy=self._policy, limiter=self._limiter, breakers=self._breakers,
            state=self._state, builder=self._builder, chain=self._chain,
            metrics=RotatorMetrics() if enable_metrics else None,
            classifier=error_classifier or ErrorClassifier(),
            logger=self._logger, sync=self._SYNC,
        )
        self._engine.unified = bool(unified_response)

        self._log_initialization_summary()

    _SYNC = True

    @staticmethod
    def _http_settings(http: HTTPConfig | None, default_backend: str, http_backend: str, http2: bool,
                       http_client_kwargs: dict[str, Any] | None, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Resolves ``http=HTTPConfig(...)`` against the flat HTTP arguments (sets kwargs['pool_size'])."""
        settings = merge_config("http", http, {
            "http_backend": http_backend, "http2": http2, "http_client_kwargs": http_client_kwargs,
            "pool_size": kwargs.get("pool_size", DEFAULT_POOL_SIZE),
        }, flat_defaults={"http_backend": default_backend})
        kwargs["pool_size"] = settings["pool_size"]
        return settings

    def _defer_provider_keys(self) -> bool:
        """Should provider keys be loaded on first use instead of in the constructor?"""
        return False

    def _log_initialization_summary(self) -> None:
        if self._keys_pending:
            self.logger.info("Rotator initialized; keys will be loaded from the secret provider on first use")
        else:
            self.logger.info(
                f"Rotator initialized with {self.key_count} keys. "
                f"Max retries: {self.max_retries}, Base delay: {self.base_delay}s, "
                f"Strategy: {type(self.rotation_strategy).__name__}"
            )
        if self.middlewares:
            self.logger.info(f"Middlewares loaded: {len(self.middlewares)}")

    @property
    def auth(self) -> str | tuple[str, str] | bool | None:
        return self._builder.auth

    @auth.setter
    def auth(self, auth: str | tuple[str, str] | bool | None) -> None:
        self._builder.auth = auth
        self._pool.reset_auth()  # the new header must prove itself before keys are removed

    @property
    def header_callback(self) -> Callable | None:
        return self._builder.header_callback

    @header_callback.setter
    def header_callback(self, callback: Callable | None) -> None:
        self._builder.header_callback = callback
        self._pool.reset_auth()

    @property
    def logger(self) -> logging.Logger:
        return self._logger

    @logger.setter
    def logger(self, logger: logging.Logger) -> None:
        self._logger = logger
        for component in (self._pool, self._state, self._chain, self._engine):
            component.logger = logger

    # ------------------------------------------------------------------
    # Keys management
    # ------------------------------------------------------------------

    @property
    def key_manager(self) -> KeyPool:
        """The key pool (keys, per-key metrics, rotation strategy)."""
        return self._pool

    @property
    def rotation_strategy(self) -> BaseRotationStrategy | None:
        return self._pool.strategy

    @rotation_strategy.setter
    def rotation_strategy(self, strategy: BaseRotationStrategy) -> None:
        self._pool.strategy = strategy

    @property
    def keys(self) -> list[str]:
        return self._pool.keys()

    @keys.setter
    def keys(self, new_keys: list[str]) -> None:
        cleaned = parse_keys(list(new_keys), logger=self.logger)
        self._pool.replace(cleaned)
        self._state.forget_except(cleaned)
        if cleaned:
            self._keys_pending = False

    @property
    def _key_metrics(self) -> dict[str, KeyMetrics]:
        return self._pool.metric_objects()

    @property
    def key_count(self) -> int:
        return self._pool.count()

    def get_next_key(self) -> str:
        key = self._pool.select()
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug("Selected key: %s", mask_key(key))
        return key

    def get_next_user_agent(self) -> str | None:
        return self._builder.next_user_agent()

    def get_next_proxy(self) -> str | None:
        return self._builder.next_proxy()

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
        new_keys = self._state.filter_invalid(list(new_keys or []))
        if not new_keys:
            self.logger.warning("Secret provider returned no usable keys; keeping current keys")
            return self.keys
        if new_keys != self.keys:
            self.keys = new_keys
            self.logger.info(f"Keys refreshed from provider: {self.key_count} keys active")
        return self.keys

    def refresh_keys_from_provider_sync(self) -> list[str]:
        """Synchronous version of refresh_keys_from_provider()."""
        return run_coroutine_sync(self.refresh_keys_from_provider)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_metrics(self) -> dict:
        return self.metrics.get_metrics() if self.metrics else {}

    def get_key_statistics(self) -> dict:
        return self._pool.metrics_dict()

    def get_circuit_states(self) -> dict[str, str]:
        """Circuit breaker state per host ('CLOSED' / 'OPEN' / 'HALF_OPEN')."""
        return self._breakers.states()

    def reset_key_health(self, key: str | None = None) -> None:
        self._pool.reset_health(key)

    def export_config(self) -> dict[str, Any]:
        config = {
            'keys_count': self.key_count,
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
            stats = self._pool.metrics_dict()
            labels = unique_labels(stats)
            config['key_statistics'] = {labels[key]: key_metrics for key, key_metrics in stats.items()}
        return config

    # ------------------------------------------------------------------
    # Backwards-compatible helpers (0.8.0 internals used by existing code)
    # ------------------------------------------------------------------

    def _calculate_backoff_delay(self, attempt: int) -> float:
        return self._policy.backoff(attempt)

    def _infer_auth_header(self, key: str) -> tuple[str, str]:
        return infer_auth_header(key)

    def _prepare_headers_and_cookies(self, key: str, custom_headers: dict[str, str] | None,
                                     url: str) -> tuple[dict[str, str], dict[str, str]]:
        return self._builder.headers_and_cookies(key, custom_headers, url)

    @staticmethod
    def _get_domain_from_url(url: str) -> str:
        return host_of(url) if url else ""

    @staticmethod
    def _validate_url(url: str) -> None:
        if not url or not url.strip():
            raise ValueError("URL cannot be empty")


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

    _SYNC = True

    def __init__(self, *args: Any, http_backend: str = "requests", http2: bool = False,
                 http_client_kwargs: dict[str, Any] | None = None, http: HTTPConfig | None = None,
                 **kwargs: Any):
        h = self._http_settings(http, "requests", http_backend, http2, http_client_kwargs, kwargs)
        super().__init__(*args, **kwargs)
        self._transport: SyncTransport = create_sync_transport(
            h["http_backend"], self.pool_size, h["http2"], h["http_client_kwargs"]
        )
        self._engine.status_of = self._transport.status
        self.http_backend = self._transport.name
        self._chain.warn_async_only()
        self._refresh_stop: threading.Event | None = None
        self._refresh_thread: threading.Thread | None = None
        if self.auto_refresh_interval is not None:
            self.start_auto_refresh(self.auto_refresh_interval)
        self.logger.info(f"Sync rotator initialized ({self.http_backend} backend, connection pooling)")

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

    # --- request ---

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response | UnifiedResponse:
        self._validate_url(url)
        if self._logger.isEnabledFor(logging.DEBUG):
            self._logger.debug("Initiating %s request to %s", method, url)
        response: requests.Response | UnifiedResponse = self._drive(self._engine.run(method, url, kwargs))
        return response

    def _drive(self, flow: Flow) -> Any:
        """Performs the engine's effects with blocking I/O."""
        transport = self._transport
        network_errors = transport.network_errors
        chain = self._chain
        value: Any = None
        error: BaseException | None = None
        while True:
            try:
                effect = flow.send(value) if error is None else flow.throw(error)
            except StopIteration as stop:  # pragma: no cover - flows end with DONE/SHORT
                return stop.value
            error = None
            tag = effect[0]
            try:
                if tag == SEND:
                    try:
                        value = transport.request(effect[1], effect[2], effect[3], effect[4], effect[5])
                    except network_errors as e:
                        value = NetworkFailure(e, transport.is_safe_to_retry_error(e))
                elif tag == DONE:
                    return effect[1]
                elif tag == SHORT:  # middleware short-circuit (e.g. cache hit)
                    if self._engine.unified:
                        return UnifiedResponse.from_info(effect[1], effect[2])
                    return build_sync_response(effect[1], effect[2], transport.name)
                elif tag == SLEEP:
                    time.sleep(effect[1])
                    value = None
                elif tag == READ:
                    try:
                        value = effect[1].content
                    except network_errors as e:
                        value = NetworkFailure(e, transport.is_safe_to_retry_error(e))
                elif tag == RELEASE:
                    transport.close_response(effect[1])
                    value = None
                elif tag == BEFORE:
                    value = chain.before_sync(effect[1], effect[2])
                elif tag == AFTER:
                    chain.after_sync(effect[1])
                    value = None
                elif tag == ON_ERROR:
                    chain.on_error_sync(effect[1])
                    value = None
                elif tag == CALL:
                    value = effect[1](*effect[2])
                else:  # pragma: no cover - engine bug
                    raise RuntimeError(f"Unknown effect {tag!r}")
            except BaseException as e:  # deliver into the engine so its cleanup runs
                error, value = e, None

    def get(self, url: str, **kwargs: Any) -> requests.Response | UnifiedResponse:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> requests.Response | UnifiedResponse:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> requests.Response | UnifiedResponse:
        return self.request("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> requests.Response | UnifiedResponse:
        return self.request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> requests.Response | UnifiedResponse:
        return self.request("DELETE", url, **kwargs)

    def head(self, url: str, **kwargs: Any) -> requests.Response | UnifiedResponse:
        return self.request("HEAD", url, **kwargs)


# ============================================================================
# ASYNC ROTATOR
# ============================================================================

class AsyncAPIKeyRotator(BaseKeyRotator):
    """
    Asynchronous rotator.

    Args (in addition to BaseKeyRotator):
        http_backend: 'aiohttp' (default) or 'httpx'.
        http2: Enable HTTP/2 (httpx backend only).
        http_client_kwargs: Extra settings for the HTTP client session.

    When created inside a running event loop with a ``secret_provider`` and no
    ``api_keys``, keys are loaded on first use (``async with`` or the first
    request) in that loop - the constructor never blocks the loop and the
    provider runs on the loop it belongs to. Call ``await rotator.load_keys()``
    to load them explicitly.
    """

    _SYNC = False

    def __init__(self, *args: Any, http_backend: str = "aiohttp", http2: bool = False,
                 http_client_kwargs: dict[str, Any] | None = None, http: HTTPConfig | None = None,
                 **kwargs: Any):
        h = self._http_settings(http, "aiohttp", http_backend, http2, http_client_kwargs, kwargs)
        super().__init__(*args, **kwargs)
        self._transport: AsyncTransport = create_async_transport(
            h["http_backend"], self.pool_size, self.timeout, h["http2"], h["http_client_kwargs"]
        )
        self._engine.status_of = self._transport.status
        self.http_backend = self._transport.name
        self._refresh_task: asyncio.Task | None = None
        self._keys_lock = asyncio.Lock()
        self.logger.info(f"Async rotator initialized ({self.http_backend} backend)")

    def _defer_provider_keys(self) -> bool:
        return in_running_loop()

    async def load_keys(self) -> list[str]:
        """Loads keys from the secret provider if that is still pending; returns the active keys."""
        if self._keys_pending:
            async with self._keys_lock:
                if self._keys_pending:
                    assert self.secret_provider is not None   # _keys_pending is only set with one
                    provider_keys = await self.secret_provider.get_keys()
                    if not provider_keys:
                        self.logger.warning(
                            "Secret provider returned no keys, falling back to environment variable")
                    keys = parse_keys(list(provider_keys) if provider_keys else None,
                                      self._env_var, self.logger)
                    if not keys:
                        raise ValueError("At least one API key is required")
                    self.keys = keys
                    self._log_initialization_summary()
        return self.keys

    @property
    def _session(self) -> Any:
        """The underlying client session (aiohttp.ClientSession / httpx.AsyncClient) or None."""
        return self._transport.session

    @_session.setter
    def _session(self, value: Any) -> None:
        self._transport.session = value

    async def __aenter__(self):
        await self.load_keys()
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

    # --- request ---

    async def request(self, method: str, url: str, **kwargs: Any) -> aiohttp.ClientResponse | UnifiedResponse:
        self._validate_url(url)
        if self._logger.isEnabledFor(logging.DEBUG):
            self._logger.debug("Initiating async %s request to %s", method, url)
        if self._keys_pending:
            await self.load_keys()
        self._ensure_background_tasks()
        response: aiohttp.ClientResponse | UnifiedResponse = await self._drive(self._engine.run(method, url, kwargs))
        return response

    async def _drive(self, flow: Flow) -> Any:
        """Performs the engine's effects with asyncio."""
        transport = self._transport
        network_errors = transport.network_errors
        chain = self._chain
        value: Any = None
        error: BaseException | None = None
        while True:
            try:
                effect = flow.send(value) if error is None else flow.throw(error)
            except StopIteration as stop:  # pragma: no cover - flows end with DONE/SHORT
                return stop.value
            error = None
            tag = effect[0]
            try:
                if tag == SEND:
                    try:
                        value = await transport.request(effect[1], effect[2], effect[3], effect[4], effect[5])
                    except network_errors as e:
                        value = NetworkFailure(e, transport.is_safe_to_retry_error(e))
                elif tag == DONE:
                    return effect[1]
                elif tag == SHORT:  # middleware short-circuit (e.g. cache hit)
                    if self._engine.unified:
                        return UnifiedResponse.from_info(effect[1], effect[2])
                    return build_async_response(effect[1], effect[2])
                elif tag == SLEEP:
                    await asyncio.sleep(effect[1])
                    value = None
                elif tag == READ:
                    try:
                        value = await transport.read(effect[1])
                    except network_errors as e:
                        value = NetworkFailure(e, transport.is_safe_to_retry_error(e))
                elif tag == RELEASE:
                    await transport.release(effect[1])
                    value = None
                elif tag == BEFORE:
                    value = await chain.before(effect[1], effect[2])
                elif tag == AFTER:
                    await chain.after(effect[1])
                    value = None
                elif tag == ON_ERROR:
                    await chain.on_error(effect[1])
                    value = None
                elif tag == CALL:
                    value = await asyncio.to_thread(effect[1], *effect[2])
                else:  # pragma: no cover - engine bug
                    raise RuntimeError(f"Unknown effect {tag!r}")
            except BaseException as e:  # deliver into the engine so its cleanup runs
                error, value = e, None

    async def get(self, url: str, **kwargs: Any) -> aiohttp.ClientResponse | UnifiedResponse:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> aiohttp.ClientResponse | UnifiedResponse:
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> aiohttp.ClientResponse | UnifiedResponse:
        return await self.request("PUT", url, **kwargs)

    async def patch(self, url: str, **kwargs: Any) -> aiohttp.ClientResponse | UnifiedResponse:
        return await self.request("PATCH", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> aiohttp.ClientResponse | UnifiedResponse:
        return await self.request("DELETE", url, **kwargs)

    async def head(self, url: str, **kwargs: Any) -> aiohttp.ClientResponse | UnifiedResponse:
        return await self.request("HEAD", url, **kwargs)
