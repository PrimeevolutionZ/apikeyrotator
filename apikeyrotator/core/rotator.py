import time
import requests
import asyncio
import aiohttp
import logging
import random
import threading
from dataclasses import dataclass  # Добавлен недостающий импорт
from typing import Any, List, Optional, Dict, Union, Callable, Tuple
from contextlib import asynccontextmanager
from urllib.parse import urlparse

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


@dataclass
class _ResponseCodeWrapper:
    """Wrapper for status code to simulate response object behavior for classifier"""
    status_code: int
    headers: Dict[str, str] = None

    def __init__(self, status_code: int, headers: Dict[str, str] = None):
        self.status_code = status_code
        self.headers = headers or {}


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
                if key in self._key_metrics:
                    del self._key_metrics[key]
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

    def update_metrics(self, key: str, success: bool, response_time: float, is_rate_limited: bool = False) -> None:
        with self._lock:
            if key in self._key_metrics:
                self._key_metrics[key].update_from_request(
                    success=success,
                    response_time=response_time,
                    is_rate_limited=is_rate_limited
                )

    def reset_health(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key:
                if key in self._key_metrics:
                    self._key_metrics[key].is_healthy = True
                    self._key_metrics[key].consecutive_failures = 0
            else:
                for metrics in self._key_metrics.values():
                    metrics.is_healthy = True
                    metrics.consecutive_failures = 0

    def reinit_keys(self, new_keys: List[str]) -> None:
        with self._lock:
            self._keys = new_keys.copy()
            self._key_metrics = {key: KeyMetrics(key) for key in self._keys}


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
    ):
        self.logger = logger if logger else _setup_default_logger()

        if load_env_file and _DOTENV_INSTALLED:
            load_dotenv()

        self.secret_provider = secret_provider

        keys = parse_keys(api_keys, env_var, self.logger)
        if not keys:
            raise ValueError("At least one API key is required")

        self.key_manager = _ThreadSafeKeyManager(keys, self.logger)

        self.max_retries = max_retries
        self.base_delay = base_delay
        self.timeout = timeout
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

        self.config_loader = config_loader or ConfigLoader(config_file=config_file, logger=self.logger)
        self.config = self.config_loader.load_config()

        self.rotation_strategy_kwargs = rotation_strategy_kwargs or {}
        self._init_rotation_strategy(rotation_strategy)

        self.middlewares = middlewares or []
        self.enable_metrics = enable_metrics
        self.metrics = RotatorMetrics() if enable_metrics else None

        self._log_initialization_summary()

    def _init_rotation_strategy(self, rotation_strategy: Union[str, RotationStrategy, BaseRotationStrategy]) -> None:
        if isinstance(rotation_strategy, BaseRotationStrategy):
            self.rotation_strategy = rotation_strategy
        else:
            self.rotation_strategy = create_rotation_strategy(
                rotation_strategy,
                self.key_manager.get_keys(),
                **self.rotation_strategy_kwargs
            )

    def _log_initialization_summary(self) -> None:
        self.logger.info(
            f"✅ Ротатор инициализирован с {self.key_manager.get_key_count()} ключами. "
            f"Макс попыток: {self.max_retries}, Базовая задержка: {self.base_delay}s, "
            f"Стратегия: {type(self.rotation_strategy).__name__}"
        )
        if self.middlewares:
            self.logger.info(f"✅ Загружено middleware: {len(self.middlewares)}")

    @property
    def keys(self) -> List[str]:
        return self.key_manager.get_keys()

    @keys.setter
    def keys(self, new_keys: List[str]):
        self.key_manager.reinit_keys(new_keys)
        if hasattr(self.rotation_strategy, 'update_keys'):
            self.rotation_strategy.update_keys(new_keys)

    @property
    def _key_metrics(self) -> Dict[str, KeyMetrics]:
        return self.key_manager.get_metric_objects()

    def get_metrics(self) -> Dict:
        return self.metrics.get_metrics() if self.metrics else {}

    def get_key_statistics(self) -> Dict:
        return self.key_manager.get_metrics()

    def reset_key_health(self, key: Optional[str] = None):
        self.key_manager.reset_health(key)

    @staticmethod
    def _get_domain_from_url(url: str) -> str:
        try:
            return urlparse(url).netloc
        except (ValueError, AttributeError):
            return ""

    def _infer_auth_header(self, key: str) -> Tuple[str, str]:
        for prefix in API_KEY_PATTERNS['bearer']:
            if key.startswith(prefix):
                return DEFAULT_AUTH_HEADERS['bearer'], f"Bearer {key}"
        if len(key) == API_KEY_PATTERNS['api_key']:
            return DEFAULT_AUTH_HEADERS['api_key'], key
        return DEFAULT_AUTH_HEADERS['bearer'], f"Key {key}"

    def get_next_key(self) -> str:
        keys = self.key_manager.get_keys()
        if not keys:
            raise AllKeysExhaustedError("Нет доступных ключей")

        metrics_objects = self.key_manager.get_metric_objects()
        key = self.rotation_strategy.get_next_key(metrics_objects)

        self.logger.debug(f"Выбран ключ: {key[:KEY_LOG_LENGTH]}{KEY_LOG_SUFFIX}")
        return key

    def get_next_user_agent(self) -> Optional[str]:
        if not self.user_agents:
            return None
        ua = self.user_agents[self._ua_index]
        self._ua_index = (self._ua_index + 1) % len(self.user_agents)
        return ua

    def get_next_proxy(self) -> Optional[str]:
        if not self.proxy_list:
            return None
        proxy = self.proxy_list[self._proxy_index]
        self._proxy_index = (self._proxy_index + 1) % len(self.proxy_list)
        return proxy

    def _prepare_headers_and_cookies(
            self, key: str, custom_headers: Optional[Dict[str, str]], url: str
    ) -> Tuple[Dict[str, str], Dict[str, str]]:
        headers = custom_headers.copy() if custom_headers else {}
        cookies = {}
        domain = self._get_domain_from_url(url)

        if self.save_sensitive_headers and domain:
            saved = self.config.get("successful_headers", {}).get(domain, {})
            safe_headers = {k: v for k, v in saved.items() if k not in ["Authorization", "X-API-Key"]}
            headers.update(safe_headers)

        if self.header_callback:
            result = self.header_callback(key, custom_headers)
            if isinstance(result, tuple) and len(result) == 2:
                headers.update(result[0])
                cookies.update(result[1])
            elif isinstance(result, dict):
                headers.update(result)

        if "Authorization" not in headers:
            header_name, header_value = self._infer_auth_header(key)
            headers[header_name] = header_value

        user_agent = self.get_next_user_agent()
        if user_agent and "User-Agent" not in headers:
            headers["User-Agent"] = user_agent

        return headers, cookies

    def _apply_random_delay(self) -> None:
        if not self.random_delay_range:
            return
        delay = random.uniform(self.random_delay_range[0], self.random_delay_range[1])
        time.sleep(delay + random.uniform(0, delay * 0.1))

    async def _apply_random_delay_async(self) -> None:
        if not self.random_delay_range:
            return
        delay = random.uniform(self.random_delay_range[0], self.random_delay_range[1])
        await asyncio.sleep(delay + random.uniform(0, delay * 0.1))

    def _calculate_backoff_delay(self, attempt: int) -> float:
        delay = self.base_delay * (2 ** attempt)
        return delay + random.uniform(0, delay * 0.1)

    @property
    def key_count(self) -> int:
        return self.key_manager.get_key_count()


# ============================================================================
# SYNC ROTATOR
# ============================================================================

class APIKeyRotator(BaseKeyRotator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=100, pool_maxsize=100, max_retries=0)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.logger.info("✅ Синхронный ротатор инициализирован с Connection Pooling")

    def export_config(self) -> Dict[str, Any]:
        config = {
            'keys_count': self.key_manager.get_key_count(),
            'max_retries': self.max_retries,
            'base_delay': self.base_delay,
            'timeout': self.timeout,
            'strategy': self.rotation_strategy.__class__.__name__,
            'metrics_enabled': self.metrics is not None,
        }
        if self.metrics:
            config['key_statistics'] = {}
            for key in self.key_manager.get_keys():
                key_metrics = self.key_manager.get_metrics(key)
                if key_metrics:
                    safe_key = f"{key[:4]}****" if len(key) > 4 else "****"
                    config['key_statistics'][safe_key] = key_metrics
        return config

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        if not url or not url.strip():
            raise ValueError("URL cannot be empty")

        self.logger.info(f"Инициирован {method} запрос к {url}")
        domain = self._get_domain_from_url(url)
        start_time = time.time()

        retry_attempt = 0

        while True:
            if retry_attempt >= self.max_retries:
                self.logger.error(f"❌ Все {self.max_retries} попыток исчерпаны")
                raise AllKeysExhaustedError(f"Все ключи исчерпаны после {self.max_retries} попыток")

            if self.key_count == 0:
                raise AllKeysExhaustedError("Все ключи невалидны (список пуст)")

            try:
                key = self.get_next_key()
            except AllKeysExhaustedError:
                raise

            headers, cookies = self._prepare_headers_and_cookies(key, kwargs.get("headers"), url)
            request_kwargs = kwargs.copy()
            request_kwargs["headers"] = headers
            request_kwargs["cookies"] = cookies
            request_kwargs["timeout"] = kwargs.get("timeout", self.timeout)

            proxy = self.get_next_proxy()
            if proxy:
                request_kwargs["proxies"] = {"http": proxy, "https": proxy}

            self._apply_random_delay()

            request_info = RequestInfo(
                method=method, url=url, headers=headers, cookies=cookies,
                key=key, attempt=retry_attempt, kwargs=request_kwargs
            )

            for middleware in self.middlewares:
                if not asyncio.iscoroutinefunction(middleware.before_request):
                    request_info = middleware.before_request(request_info)
                    request_kwargs["headers"] = request_info.headers
                    request_kwargs["cookies"] = request_info.cookies

            try:
                response = self.session.request(method, url, **request_kwargs)
                request_time = time.time() - start_time

                response_info = ResponseInfo(
                    status_code=response.status_code, headers=dict(response.headers),
                    content=response.content, request_info=request_info
                )
                for middleware in self.middlewares:
                    if not asyncio.iscoroutinefunction(middleware.after_request):
                        response_info = middleware.after_request(response_info)

                error_type = self.error_classifier.classify_error(response=response)

                is_success = error_type not in [ErrorType.RATE_LIMIT, ErrorType.TEMPORARY, ErrorType.PERMANENT]
                is_rate_limited = (error_type == ErrorType.RATE_LIMIT)

                if self.metrics:
                    self.metrics.record_request(
                        key=key, endpoint=url, success=is_success,
                        response_time=request_time, is_rate_limited=is_rate_limited
                    )
                self.key_manager.update_metrics(key, is_success, request_time, is_rate_limited)

                if error_type == ErrorType.PERMANENT:
                    self.logger.error(
                        f"❌ Ключ {key[:KEY_LOG_LENGTH]}{KEY_LOG_SUFFIX} постоянно невалиден (Status: {response.status_code})")
                    self.key_manager.remove_key(key)
                    if hasattr(self.rotation_strategy, 'update_keys'):
                        self.rotation_strategy.update_keys(self.key_manager.get_keys())
                    continue

                elif error_type in [ErrorType.RATE_LIMIT, ErrorType.TEMPORARY]:
                    retry_attempt += 1
                    msg = "Rate limited" if error_type == ErrorType.RATE_LIMIT else "Временная ошибка"
                    self.logger.warning(
                        f"↻ {msg} (Status: {response.status_code}). Попытка {retry_attempt}/{self.max_retries}")

                    if retry_attempt < self.max_retries:
                        delay = self._calculate_backoff_delay(retry_attempt - 1)
                        time.sleep(delay)
                        continue
                    continue

                elif self.should_retry_callback and self.should_retry_callback(response):
                    retry_attempt += 1
                    time.sleep(self._calculate_backoff_delay(retry_attempt - 1))
                    continue

                self.logger.info(f"✅ Успешно (Status: {response.status_code})")
                return response

            except requests.RequestException as e:
                request_time = time.time() - start_time
                self.key_manager.update_metrics(key, False, request_time)
                retry_attempt += 1
                self.logger.error(f"⚠️ Ошибка сети: {e}. Попытка {retry_attempt}/{self.max_retries}")
                if retry_attempt < self.max_retries:
                    time.sleep(self._calculate_backoff_delay(retry_attempt - 1))
                    continue

    def get(self, url: str, **kwargs) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> requests.Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs) -> requests.Response:
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs) -> requests.Response:
        return self.request("DELETE", url, **kwargs)


# ============================================================================
# ASYNC ROTATOR
# ============================================================================

class AsyncAPIKeyRotator(BaseKeyRotator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._session: Optional[aiohttp.ClientSession] = None
        self.logger.info("✅ Асинхронный ротатор инициализирован")

    async def __aenter__(self):
        await self._get_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout))
        return self._session

    async def request(self, method: str, url: str, **kwargs) -> aiohttp.ClientResponse:
        if not url or not url.strip():
            raise ValueError("URL cannot be empty")

        self.logger.info(f"Инициирован async {method} запрос к {url}")
        session = await self._get_session()
        domain = self._get_domain_from_url(url)

        retry_attempt = 0

        while True:
            if retry_attempt >= self.max_retries:
                raise AllKeysExhaustedError(f"Все ключи исчерпаны после {self.max_retries} попыток")

            if self.key_count == 0:
                raise AllKeysExhaustedError("Все ключи невалидны")

            key = self.get_next_key()
            headers, cookies = self._prepare_headers_and_cookies(key, kwargs.get("headers"), url)

            request_kwargs = kwargs.copy()
            request_kwargs["headers"] = headers
            request_kwargs["cookies"] = cookies

            proxy = self.get_next_proxy()
            if proxy:
                request_kwargs["proxy"] = proxy

            await self._apply_random_delay_async()

            request_info = RequestInfo(
                method=method, url=url, headers=headers, cookies=cookies,
                key=key, attempt=retry_attempt, kwargs=request_kwargs
            )

            for middleware in self.middlewares:
                request_info = await middleware.before_request(request_info)
                request_kwargs["headers"] = request_info.headers
                request_kwargs["cookies"] = request_info.cookies

            start_time = time.time()
            try:
                response = await session.request(method, url, **request_kwargs)
                request_time = time.time() - start_time

                response_info = ResponseInfo(
                    status_code=response.status,
                    headers=dict(response.headers),
                    content=None,
                    request_info=request_info
                )

                for middleware in self.middlewares:
                    response_info = await middleware.after_request(response_info)

                error_type = self.error_classifier.classify_error(
                    response=_ResponseCodeWrapper(response.status, dict(response.headers))
                )

                is_success = error_type not in [ErrorType.RATE_LIMIT, ErrorType.TEMPORARY, ErrorType.PERMANENT]
                is_rate_limited = (error_type == ErrorType.RATE_LIMIT)

                if self.metrics:
                    self.metrics.record_request(
                        key=key, endpoint=url, success=is_success,
                        response_time=request_time, is_rate_limited=is_rate_limited
                    )
                self.key_manager.update_metrics(key, is_success, request_time, is_rate_limited)

                if error_type == ErrorType.PERMANENT:
                    self.logger.error(
                        f"❌ Ключ {key[:KEY_LOG_LENGTH]}{KEY_LOG_SUFFIX} постоянно невалиден (Status: {response.status})")
                    self.key_manager.remove_key(key)
                    if hasattr(self.rotation_strategy, 'update_keys'):
                        self.rotation_strategy.update_keys(self.key_manager.get_keys())
                    response.release()
                    continue

                elif error_type in [ErrorType.RATE_LIMIT, ErrorType.TEMPORARY]:
                    retry_attempt += 1
                    response.release()
                    if retry_attempt < self.max_retries:
                        delay = self._calculate_backoff_delay(retry_attempt - 1)
                        self.logger.warning(f"↻ Временная ошибка/RateLimit. Ожидание {delay:.2f}s")
                        await asyncio.sleep(delay)
                        continue
                    continue

                elif self.should_retry_callback and self.should_retry_callback(response.status):
                    retry_attempt += 1
                    response.release()
                    await asyncio.sleep(self._calculate_backoff_delay(retry_attempt - 1))
                    continue

                self.logger.info(f"✅ Успешно (Status: {response.status})")
                return response

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                request_time = time.time() - start_time
                self.key_manager.update_metrics(key, False, request_time)
                retry_attempt += 1
                self.logger.error(f"⚠️ Async Ошибка сети: {e}")
                if retry_attempt < self.max_retries:
                    await asyncio.sleep(self._calculate_backoff_delay(retry_attempt - 1))
                    continue

    async def get(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        return await self.request("DELETE", url, **kwargs)