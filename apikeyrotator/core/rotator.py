import time
import requests
import asyncio
import aiohttp
import logging
import random
import threading
from typing import List, Optional, Dict, Union, Callable, Tuple
from contextlib import contextmanager
from .key_parser import parse_keys
from .exceptions import AllKeysExhaustedError
from apikeyrotator.utils import async_retry_with_backoff
from apikeyrotator.strategies import (
    RotationStrategy,
    create_rotation_strategy,
    BaseRotationStrategy,
    KeyMetrics
)
from apikeyrotator.metrics import RotatorMetrics
from apikeyrotator.middleware import RotatorMiddleware, RequestInfo, ResponseInfo, ErrorInfo
from apikeyrotator.utils import ErrorClassifier, ErrorType
from .config_loader import ConfigLoader
from apikeyrotator.providers import SecretProvider

try:
    from dotenv import load_dotenv

    _DOTENV_INSTALLED = True
except ImportError:
    _DOTENV_INSTALLED = False


def _setup_default_logger():
    """Sets up the default logger"""
    logger = logging.getLogger(__name__)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


# Simple container for status code instead of MagicMock
class _StatusCodeWrapper:
    """Simple object to pass status code without MagicMock"""

    def __init__(self, status_code: int):
        self.status_code = status_code


class BaseKeyRotator:
    """
    Base class for common key rotation logic.
    Thread-safe version with fixed critical bugs.
    """

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
            save_sensitive_headers: bool = False,  # NEW: Disable saving sensitive data by default
    ):
        self.logger = logger if logger else _setup_default_logger()

        if load_env_file and _DOTENV_INSTALLED:
            self.logger.debug("Attempting to load .env file.")
            load_dotenv()
        elif load_env_file and not _DOTENV_INSTALLED:
            self.logger.warning("python-dotenv is not installed. Cannot load .env file.")

        # Initialize secret provider
        self.secret_provider = secret_provider
        if secret_provider:
            self.logger.info("Using secret provider for key management")

        # Validate and parse keys
        self.keys = parse_keys(api_keys, env_var, self.logger)
        if not self.keys:
            raise ValueError("At least one API key is required")

        self.max_retries = max_retries
        self.base_delay = base_delay
        self.timeout = timeout
        self.should_retry_callback = should_retry_callback
        self.header_callback = header_callback
        self.user_agents = user_agents if user_agents else []
        self.current_user_agent_index = 0
        self.random_delay_range = random_delay_range
        self.proxy_list = proxy_list if proxy_list else []
        self.current_proxy_index = 0
        self.config_file = config_file
        self.save_sensitive_headers = save_sensitive_headers
        self.config_loader = config_loader if config_loader else ConfigLoader(
            config_file=config_file,
            logger=self.logger
        )
        self.config = self.config_loader.load_config()
        self.error_classifier = error_classifier if error_classifier else ErrorClassifier()

        # Thread-safety: Add locks
        self._keys_lock = threading.RLock()
        self._metrics_lock = threading.RLock()
        self._ua_lock = threading.Lock()
        self._proxy_lock = threading.Lock()
        self._config_lock = threading.RLock()

        # Initialize rotation strategy
        self.rotation_strategy_kwargs = rotation_strategy_kwargs or {}
        self._init_rotation_strategy(rotation_strategy)

        # Initialize middleware
        self.middlewares = middlewares if middlewares else []

        # Initialize metrics
        self.enable_metrics = enable_metrics
        self.metrics = RotatorMetrics() if enable_metrics else None

        # Use KeyMetrics instead of KeyStats
        with self._metrics_lock:
            self._key_metrics: Dict[str, KeyMetrics] = {
                key: KeyMetrics(key) for key in self.keys
            }

        self.logger.info(
            f"✅ Rotator initialized with {len(self.keys)} keys. "
            f"Max retries: {self.max_retries}, Base delay: {self.base_delay}s, "
            f"Timeout: {self.timeout}s, Strategy: {type(self.rotation_strategy).__name__}"
        )
        if self.user_agents:
            self.logger.info(f"User-Agent rotation enabled with {len(self.user_agents)} agents.")
        if self.random_delay_range:
            self.logger.info(f"Random delay enabled: {self.random_delay_range[0]}s - {self.random_delay_range[1]}s.")
        if self.proxy_list:
            self.logger.info(f"Proxy rotation enabled with {len(self.proxy_list)} proxies.")
        if self.middlewares:
            self.logger.info(f"Loaded {len(self.middlewares)} middleware(s).")

    def _init_rotation_strategy(self, rotation_strategy: Union[str, RotationStrategy, BaseRotationStrategy]):
        """Initializes the rotation strategy"""
        if isinstance(rotation_strategy, BaseRotationStrategy):
            self.rotation_strategy = rotation_strategy
        else:
            with self._keys_lock:
                self.rotation_strategy = create_rotation_strategy(
                    rotation_strategy,
                    self.keys.copy(),  # Pass copy for thread-safety
                    **self.rotation_strategy_kwargs
                )
        self.logger.debug(f"Rotation strategy initialized: {type(self.rotation_strategy).__name__}")

    @staticmethod
    def _get_domain_from_url(url: str) -> str:
        """Extracts domain from URL"""
        from urllib.parse import urlparse
        try:
            parsed_url = urlparse(url)
            return parsed_url.netloc
        except Exception:
            return ""

    def get_next_key(self) -> str:
        """
        Get the next key according to the rotation strategy.
        Thread-safe version.
        """
        with self._keys_lock, self._metrics_lock:
            if not self.keys:
                raise AllKeysExhaustedError("No keys available")

            # Pass copy of metrics for safety
            metrics_copy = {k: v for k, v in self._key_metrics.items() if k in self.keys}
            key = self.rotation_strategy.get_next_key(metrics_copy)

        # Logging without full key (only 4 characters for safety)
        self.logger.debug(f"Selected key: {key[:4]}****")
        return key

    def get_next_user_agent(self) -> Optional[str]:
        """Get the next User-Agent (thread-safe)"""
        if not self.user_agents:
            return None
        with self._ua_lock:
            ua = self.user_agents[self.current_user_agent_index]
            self.current_user_agent_index = (self.current_user_agent_index + 1) % len(self.user_agents)
        self.logger.debug(f"Using User-Agent: {ua}")
        return ua

    def get_next_proxy(self) -> Optional[str]:
        """Get the next proxy (thread-safe)"""
        if not self.proxy_list:
            return None
        with self._proxy_lock:
            proxy = self.proxy_list[self.current_proxy_index]
            self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxy_list)
        self.logger.debug(f"Using proxy: {proxy}")
        return proxy

    def _prepare_headers_and_cookies(
            self,
            key: str,
            custom_headers: Optional[dict],
            url: str
    ) -> Tuple[dict, dict]:
        """
        Prepares headers and cookies with authorization and User-Agent rotation.
        """
        headers = custom_headers.copy() if custom_headers else {}
        cookies = {}

        domain = self._get_domain_from_url(url)

        # Apply saved headers for domain (if enabled)
        if self.save_sensitive_headers:
            with self._config_lock:
                if domain in self.config.get("successful_headers", {}):
                    self.logger.debug(f"Applying saved headers for domain: {domain}")
                    saved_headers = self.config["successful_headers"][domain].copy()
                    # Remove sensitive headers from saved
                    saved_headers.pop("Authorization", None)
                    saved_headers.pop("X-API-Key", None)
                    headers.update(saved_headers)

        # Execute header_callback if provided
        if self.header_callback:
            self.logger.debug("Executing header_callback.")
            result = self.header_callback(key, custom_headers)
            if isinstance(result, tuple) and len(result) == 2:
                headers.update(result[0])
                cookies.update(result[1])
                self.logger.debug(f"header_callback returned headers and cookies")
            elif isinstance(result, dict):
                headers.update(result)
                self.logger.debug(f"header_callback returned headers")
            else:
                self.logger.warning("header_callback returned unexpected type.")

        # Automatic authorization header detection
        if "Authorization" not in headers and not any(h.lower() == "authorization" for h in headers.keys()):
            if key.startswith("sk-") or key.startswith("pk-"):
                headers["Authorization"] = f"Bearer {key}"
                self.logger.debug(f"Inferred Authorization header: Bearer {key[:4]}****")
            elif len(key) == 32:
                headers["X-API-Key"] = key
                self.logger.debug(f"Inferred X-API-Key header: {key[:4]}****")
            else:
                headers["Authorization"] = f"Key {key}"
                self.logger.debug(f"Inferred Authorization header (default): Key {key[:4]}****")

        # Rotate User-Agent
        user_agent = self.get_next_user_agent()
        if user_agent and "User-Agent" not in headers and not any(h.lower() == "user-agent" for h in headers.keys()):
            headers["User-Agent"] = user_agent

        return headers, cookies

    def _apply_random_delay(self):
        """Applies random delay with jitter"""
        if self.random_delay_range:
            delay = random.uniform(self.random_delay_range[0], self.random_delay_range[1])
            # Add jitter to avoid thundering herd
            jitter = random.uniform(0, delay * 0.1)
            total_delay = delay + jitter
            self.logger.info(f"⏳ Applying random delay of {total_delay:.2f} seconds.")
            time.sleep(total_delay)

    def _update_key_metrics(self, key: str, success: bool, response_time: float, is_rate_limited: bool = False):
        """Updates key metrics (thread-safe)"""
        with self._metrics_lock:
            if key in self._key_metrics:
                self._key_metrics[key].update_from_request(
                    success=success,
                    response_time=response_time,
                    is_rate_limited=is_rate_limited
                )

    def _remove_key_safely(self, key: str):
        with self._keys_lock, self._metrics_lock:
            if key in self.keys:
                self.keys.remove(key)

            if key in self._key_metrics:
                del self._key_metrics[key]

            # Recreate strategy with new key list
            if self.keys:
                # Map class types to strategy names
                from apikeyrotator.strategies import (
                    RoundRobinRotationStrategy,
                    RandomRotationStrategy,
                    WeightedRotationStrategy,
                    LRURotationStrategy,
                    HealthBasedStrategy
                )

                strategy_map = {
                    RoundRobinRotationStrategy: 'round_robin',
                    RandomRotationStrategy: 'random',
                    WeightedRotationStrategy: 'weighted',
                    LRURotationStrategy: 'lru',
                    HealthBasedStrategy: 'health_based'
                }

                strategy_type = type(self.rotation_strategy)
                strategy_name = strategy_map.get(strategy_type, 'round_robin')

                self._init_rotation_strategy(strategy_name)

            self.logger.warning(f"⚠️ Key {key[:4]}**** removed from rotation. {len(self.keys)} keys remaining.")

    def reset_key_health(self, key: Optional[str] = None):
        """
        Resets health status of key(s) (thread-safe).
        """
        with self._metrics_lock:
            if key:
                if key in self._key_metrics:
                    self._key_metrics[key].is_healthy = True
                    self._key_metrics[key].consecutive_failures = 0
                    self.logger.info(f"Reset health for key: {key[:4]}****")
                else:
                    self.logger.warning(f"Key {key[:4]}**** not found in metrics")
            else:
                for k in self._key_metrics:
                    self._key_metrics[k].is_healthy = True
                    self._key_metrics[k].consecutive_failures = 0
                self.logger.info("Reset health for all keys")

    def get_key_statistics(self) -> Dict[str, Dict]:
        """
        Get statistics for all keys (thread-safe).
        """
        with self._metrics_lock:
            return {
                key: metrics.to_dict()
                for key, metrics in self._key_metrics.items()
            }

    def get_metrics(self) -> Optional[Dict]:
        """
        Get general rotator metrics.
        """
        if self.metrics:
            return self.metrics.get_metrics()
        return None

    def export_config(self) -> Dict:
        """
        Export current configuration.
        """
        with self._keys_lock:
            return {
                "keys_count": len(self.keys),
                "max_retries": self.max_retries,
                "base_delay": self.base_delay,
                "timeout": self.timeout,
                "rotation_strategy": type(self.rotation_strategy).__name__,
                "user_agents_count": len(self.user_agents),
                "proxy_count": len(self.proxy_list),
                "middlewares_count": len(self.middlewares),
                "enable_metrics": self.enable_metrics,
                "config_file": self.config_file,
                "key_statistics": self.get_key_statistics(),
            }

    async def refresh_keys_from_provider(self):
        """Refreshes keys from secret provider (thread-safe)"""
        if not self.secret_provider:
            self.logger.warning("No secret provider configured")
            return

        try:
            new_keys = await self.secret_provider.refresh_keys()
            if new_keys:
                with self._keys_lock, self._metrics_lock:
                    self.keys = new_keys
                    self._key_metrics = {key: KeyMetrics(key) for key in self.keys}
                    self._init_rotation_strategy(self.rotation_strategy)
                self.logger.info(f"Refreshed {len(new_keys)} keys from secret provider")
        except Exception as e:
            self.logger.error(f"Failed to refresh keys from provider: {e}")

    @property
    def key_count(self):
        """Number of keys"""
        with self._keys_lock:
            return len(self.keys)

    def __len__(self):
        return self.key_count

    def __repr__(self):
        return f"<{self.__class__.__name__} keys={self.key_count} retries={self.max_retries}>"


class APIKeyRotator(BaseKeyRotator):
    """
    SYNCHRONOUS API key rotator.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=100,
            pool_maxsize=100,
            max_retries=0
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.logger.info(f"✅ Sync APIKeyRotator initialized with Connection Pooling")

    def _should_retry(self, response: requests.Response) -> bool:
        """Determines whether to retry the request"""
        if self.should_retry_callback:
            return self.should_retry_callback(response)
        error_type = self.error_classifier.classify_error(response=response)
        return error_type in [ErrorType.RATE_LIMIT, ErrorType.TEMPORARY]

    def _run_sync_middleware_before_request(self, request_info: RequestInfo) -> RequestInfo:
        for middleware in self.middlewares:
            # If middleware is async, log warning
            if asyncio.iscoroutinefunction(middleware.before_request):
                self.logger.warning(f"Skipping async middleware {middleware.__class__.__name__} in sync context")
                continue
            try:
                # For sync middleware just call
                request_info = middleware.before_request(request_info)
            except TypeError:
                # If middleware returns coroutine, skip
                self.logger.warning(f"Middleware {middleware.__class__.__name__} returned coroutine in sync context")
        return request_info

    def _run_sync_middleware_after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        for middleware in self.middlewares:
            if asyncio.iscoroutinefunction(middleware.after_request):
                self.logger.warning(f"Skipping async middleware {middleware.__class__.__name__} in sync context")
                continue
            try:
                response_info = middleware.after_request(response_info)
            except TypeError:
                self.logger.warning(f"Middleware {middleware.__class__.__name__} returned coroutine in sync context")
        return response_info

    def _run_sync_middleware_on_error(self, error_info: ErrorInfo) -> bool:
        for middleware in self.middlewares:
            if asyncio.iscoroutinefunction(middleware.on_error):
                self.logger.warning(f"Skipping async middleware {middleware.__class__.__name__} in sync context")
                continue
            try:
                if middleware.on_error(error_info):
                    return True
            except TypeError:
                self.logger.warning(f"Middleware {middleware.__class__.__name__} returned coroutine in sync context")
        return False

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        Executes a request. Just like requests, but with key rotation!
        """
        if not url or not url.strip():
            raise ValueError("URL cannot be empty")

        self.logger.info(f"Initiating {method} request to {url} with key rotation.")

        domain = self._get_domain_from_url(url)
        start_time = time.time()

        attempt = 0
        while attempt < self.max_retries:
            key = self.get_next_key()
            headers, cookies = self._prepare_headers_and_cookies(key, kwargs.get("headers"), url)
            kwargs["headers"] = headers
            kwargs["cookies"] = cookies
            kwargs["timeout"] = kwargs.get("timeout", self.timeout)

            proxy = self.get_next_proxy()
            if proxy:
                kwargs["proxies"] = {"http": proxy, "https": proxy}
                self.logger.info(f"🌐 Using proxy: {proxy} for attempt {attempt + 1}/{self.max_retries}.")

            self._apply_random_delay()

            # Middleware: before_request (sync version)
            request_info = RequestInfo(
                method=method,
                url=url,
                headers=headers,
                cookies=cookies,
                key=key,
                attempt=attempt,
                kwargs=kwargs
            )

            if self.middlewares:
                request_info = self._run_sync_middleware_before_request(request_info)
                kwargs["headers"] = request_info.headers
                kwargs["cookies"] = request_info.cookies

            try:
                self.logger.debug(f"Attempt {attempt + 1}/{self.max_retries} with key {key[:4]}****")
                response_obj = self.session.request(method, url, **kwargs)
                request_time = time.time() - start_time

                self.logger.debug(f"Received response with status code: {response_obj.status_code}")

                # Middleware: after_request (sync version)
                response_info = ResponseInfo(
                    status_code=response_obj.status_code,
                    headers=dict(response_obj.headers),
                    content=response_obj.content,
                    request_info=request_info
                )

                if self.middlewares:
                    response_info = self._run_sync_middleware_after_request(response_info)

                error_type = self.error_classifier.classify_error(response=response_obj)

                # Update metrics
                if self.metrics:
                    self.metrics.record_request(
                        key=key,
                        endpoint=url,
                        success=(error_type not in [ErrorType.RATE_LIMIT, ErrorType.TEMPORARY, ErrorType.PERMANENT]),
                        response_time=request_time,
                        is_rate_limited=(error_type == ErrorType.RATE_LIMIT)
                    )

                # Update key metrics
                is_rate_limited = (error_type == ErrorType.RATE_LIMIT)
                success = (error_type not in [ErrorType.RATE_LIMIT, ErrorType.TEMPORARY, ErrorType.PERMANENT])
                self._update_key_metrics(key, success, request_time, is_rate_limited)

                if error_type == ErrorType.PERMANENT:
                    self.logger.error(
                        f"❌ Key {key[:4]}**** is permanently invalid (Status: {response_obj.status_code}).")
                    self._remove_key_safely(key)
                    if not self.keys:
                        raise AllKeysExhaustedError("All keys are permanently invalid.")
                    # Don't increment attempt counter for invalid keys - try next key immediately
                    continue
                elif error_type == ErrorType.RATE_LIMIT:
                    self.logger.warning(
                        f"↻ Attempt {attempt + 1}/{self.max_retries}. Key {key[:4]}**** rate limited. Retrying with next key...")
                elif error_type == ErrorType.TEMPORARY:
                    self.logger.warning(
                        f"↻ Attempt {attempt + 1}/{self.max_retries}. Key {key[:4]}**** temporary error. Retrying...")
                elif not self._should_retry(response_obj):
                    self.logger.info(f"✅ Request successful with key {key[:4]}**** Status: {response_obj.status_code}")

                    # Save NON-sensitive headers if enabled
                    if self.save_sensitive_headers:
                        with self._config_lock:
                            if domain not in self.config.get("successful_headers", {}):
                                safe_headers = headers.copy()
                                safe_headers.pop("Authorization", None)
                                safe_headers.pop("X-API-Key", None)
                                self.config.setdefault("successful_headers", {})[domain] = safe_headers
                                self.config_loader.save_config(self.config)
                                self.logger.debug(f"Saved non-sensitive headers for domain: {domain}")

                    return response_obj

                self.logger.warning(
                    f"↻ Attempt {attempt + 1}/{self.max_retries}. Retrying...")

            except requests.RequestException as e:
                error_type = self.error_classifier.classify_error(exception=e)

                # Middleware: on_error (sync version)
                error_info = ErrorInfo(exception=e, request_info=request_info)
                if self.middlewares:
                    handled = self._run_sync_middleware_on_error(error_info)
                    if handled:
                        self.logger.info(f"Error handled by middleware")
                        continue

                # Update key metrics on error
                request_time = time.time() - start_time
                self._update_key_metrics(key, False, request_time)

                if error_type == ErrorType.NETWORK:
                    self.logger.error(
                        f"⚠️ Network error with key {key[:4]}**** on attempt {attempt + 1}/{self.max_retries}: {e}")
                else:
                    self.logger.error(
                        f"⚠️ Request exception with key {key[:4]}**** on attempt {attempt + 1}/{self.max_retries}: {e}")

            # Increment attempt counter
            attempt += 1

            if attempt < self.max_retries:
                # FIXED: Exponential backoff with jitter
                delay = self.base_delay * (2 ** (attempt - 1))
                jitter = random.uniform(0, delay * 0.1)
                total_delay = delay + jitter
                self.logger.info(f"Waiting for {total_delay:.2f} seconds before next attempt.")
                time.sleep(total_delay)

        self.logger.error(f"❌ All {len(self.keys)} keys exhausted after {self.max_retries} attempts each for {url}.")
        raise AllKeysExhaustedError(f"All {len(self.keys)} keys exhausted after {self.max_retries} attempts each")

    def get(self, url, **kwargs):
        """GET request"""
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        """POST request"""
        return self.request("POST", url, **kwargs)

    def put(self, url, **kwargs):
        """PUT request"""
        return self.request("PUT", url, **kwargs)

    def delete(self, url, **kwargs):
        """DELETE request"""
        return self.request("DELETE", url, **kwargs)


class AsyncAPIKeyRotator(BaseKeyRotator):
    """
    ASYNCHRONOUS API key rotator.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._session: Optional[aiohttp.ClientSession] = None
        self.logger.info(f"✅ Async APIKeyRotator initialized")

    async def __aenter__(self):
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            self.logger.info("Closing aiohttp client session.")
            await self._session.close()

    async def _get_session(self) -> aiohttp.ClientSession:
        """Gets or creates a session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout))
            self.logger.debug("Created new aiohttp client session.")
        return self._session

    def _should_retry(self, status: int) -> bool:
        if self.should_retry_callback:
            return self.should_retry_callback(status)
        error_type = self.error_classifier.classify_error(response=_StatusCodeWrapper(status))
        return error_type in [ErrorType.RATE_LIMIT, ErrorType.TEMPORARY]

    async def request(self, method: str, url: str, **kwargs) -> aiohttp.ClientResponse:
        """
        Executes an async request.
        """
        if not url or not url.strip():
            raise ValueError("URL cannot be empty")

        self.logger.info(f"Initiating async {method} request to {url} with key rotation.")
        session = await self._get_session()

        domain = self._get_domain_from_url(url)

        async def _perform_single_request_with_key_coroutine():
            key = self.get_next_key()
            headers, cookies = self._prepare_headers_and_cookies(key, kwargs.get("headers"), url)
            request_kwargs = kwargs.copy()
            request_kwargs["headers"] = headers
            request_kwargs["cookies"] = cookies

            proxy = self.get_next_proxy()
            if proxy:
                request_kwargs["proxy"] = proxy
                self.logger.info(f"🌐 Using proxy: {proxy} for current request.")

            if self.random_delay_range:
                delay = random.uniform(self.random_delay_range[0], self.random_delay_range[1])
                jitter = random.uniform(0, delay * 0.1)
                total_delay = delay + jitter
                self.logger.info(f"⏳ Applying random delay of {total_delay:.2f} seconds.")
                await asyncio.sleep(total_delay)

            # Middleware: before_request
            request_info = RequestInfo(
                method=method,
                url=url,
                headers=headers,
                cookies=cookies,
                key=key,
                attempt=0,
                kwargs=request_kwargs
            )

            for middleware in self.middlewares:
                request_info = await middleware.before_request(request_info)
                request_kwargs["headers"] = request_info.headers
                request_kwargs["cookies"] = request_info.cookies

            start_time = time.time()
            self.logger.debug(f"Performing async request with key {key[:4]}****")
            response_obj = await session.request(method, url, **request_kwargs)
            request_time = time.time() - start_time

            self.logger.debug(f"Received async response with status code: {response_obj.status}")

            # Middleware: after_request
            response_info = ResponseInfo(
                status_code=response_obj.status,
                headers=dict(response_obj.headers),
                content=None,
                request_info=request_info
            )

            for middleware in self.middlewares:
                response_info = await middleware.after_request(response_info)

            error_type = self.error_classifier.classify_error(response=_StatusCodeWrapper(response_obj.status))

            # Update metrics
            if self.metrics:
                self.metrics.record_request(
                    key=key,
                    endpoint=url,
                    success=(error_type not in [ErrorType.RATE_LIMIT, ErrorType.TEMPORARY, ErrorType.PERMANENT]),
                    response_time=request_time,
                    is_rate_limited=(error_type == ErrorType.RATE_LIMIT)
                )

            # Update key metrics
            is_rate_limited = (error_type == ErrorType.RATE_LIMIT)
            success = (error_type not in [ErrorType.RATE_LIMIT, ErrorType.TEMPORARY, ErrorType.PERMANENT])
            self._update_key_metrics(key, success, request_time, is_rate_limited)

            if error_type == ErrorType.PERMANENT:
                self.logger.error(
                    f"❌ Key {key[:4]}**** is permanently invalid (Status: {response_obj.status}).")
                self._remove_key_safely(key)
                await response_obj.release()
                if not self.keys:
                    raise AllKeysExhaustedError("All keys are permanently invalid.")
                raise aiohttp.ClientError("Permanent key error, try next key.")
            elif error_type == ErrorType.RATE_LIMIT:
                self.logger.warning(
                    f"↻ Key {key[:4]}**** rate limited (Status: {response_obj.status}).")
                await response_obj.release()
                raise aiohttp.ClientError("Rate limit hit, try next key.")
            elif error_type == ErrorType.TEMPORARY:
                self.logger.warning(f"↻ Key {key[:4]}**** temporary error (Status: {response_obj.status}).")
                await response_obj.release()
                raise aiohttp.ClientError("Temporary error, retry with same key.")
            elif not self._should_retry(response_obj.status):
                self.logger.info(f"✅ Async request successful with key {key[:4]}**** Status: {response_obj.status}")

                # Save NON-sensitive headers
                if self.save_sensitive_headers:
                    with self._config_lock:
                        if domain not in self.config.get("successful_headers", {}):
                            safe_headers = headers.copy()
                            safe_headers.pop("Authorization", None)
                            safe_headers.pop("X-API-Key", None)
                            self.config.setdefault("successful_headers", {})[domain] = safe_headers
                            self.config_loader.save_config(self.config)
                            self.logger.debug(f"Saved non-sensitive headers for domain: {domain}")

                return response_obj

            self.logger.warning(f"↻ Key {key[:4]}**** unexpected error: {response_obj.status}.")
            await response_obj.release()
            raise aiohttp.ClientError("Unexpected error, retry.")

        # Execute with retry
        final_response = await async_retry_with_backoff(
            _perform_single_request_with_key_coroutine,
            retries=len(self.keys) * self.max_retries,
            backoff_factor=self.base_delay,
            exceptions=aiohttp.ClientError
        )

        return final_response

    async def get(self, url, **kwargs) -> aiohttp.ClientResponse:
        """GET request"""
        return await self.request("GET", url, **kwargs)

    async def post(self, url, **kwargs) -> aiohttp.ClientResponse:
        """POST request"""
        return await self.request("POST", url, **kwargs)

    async def put(self, url, **kwargs) -> aiohttp.ClientResponse:
        """PUT request"""
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url, **kwargs) -> aiohttp.ClientResponse:
        """DELETE request"""
        return await self.request("DELETE", url, **kwargs)