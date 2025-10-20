import os
import time
import requests
import asyncio
import aiohttp
import logging
import random
import json
from typing import List, Optional, Dict, Union, Callable, Awaitable, Tuple
from unittest.mock import MagicMock
from .key_parser import parse_keys
from .exceptions import NoAPIKeysError, AllKeysExhaustedError
from .utils import async_retry_with_backoff
from .rotation_strategies import (
    RotationStrategy,
    create_rotation_strategy,
    BaseRotationStrategy,
    RoundRobinRotationStrategy
)
from .metrics import RotatorMetrics, KeyStats  # Импортируем KeyStats вместо KeyMetrics
from .middleware import RotatorMiddleware, RequestInfo, ResponseInfo, ErrorInfo
from .error_classifier import ErrorClassifier, ErrorType
from .config_loader import ConfigLoader
from .secret_providers import SecretProvider

try:
    from dotenv import load_dotenv

    _DOTENV_INSTALLED = True
except ImportError:
    _DOTENV_INSTALLED = False


def _setup_default_logger():
    """Настраивает логгер по умолчанию"""
    logger = logging.getLogger(__name__)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


class BaseKeyRotator:
    """
    Базовый класс для общей логики ротации ключей.

    Предоставляет основные функции для управления API ключами, включая:
    - Загрузку ключей из различных источников
    - Ротацию ключей с различными стратегиями
    - Отслеживание метрик и здоровья ключей
    - Поддержку middleware для расширяемости
    - Управление прокси и User-Agent
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
    ):
        """
        Инициализирует ротатор ключей.

        Args:
            api_keys: Список ключей или строка с разделителями-запятыми
            env_var: Имя переменной окружения для загрузки ключей
            max_retries: Максимальное количество попыток
            base_delay: Базовая задержка для экспоненциального backoff
            timeout: Таймаут запроса в секундах
            should_retry_callback: Кастомная функция определения необходимости retry
            header_callback: Кастомная функция для формирования заголовков
            user_agents: Список User-Agent для ротации
            random_delay_range: Диапазон случайной задержки (min, max)
            proxy_list: Список прокси для ротации
            logger: Кастомный логгер
            config_file: Путь к файлу конфигурации
            load_env_file: Загружать ли .env файл
            error_classifier: Классификатор ошибок
            config_loader: Загрузчик конфигурации
            rotation_strategy: Стратегия ротации ключей
            rotation_strategy_kwargs: Параметры для стратегии ротации
            middlewares: Список middleware для обработки запросов
            secret_provider: Провайдер секретов для получения ключей
            enable_metrics: Включить сбор метрик
        """
        self.logger = logger if logger else _setup_default_logger()

        if load_env_file and _DOTENV_INSTALLED:
            self.logger.debug("Attempting to load .env file.")
            load_dotenv()
        elif load_env_file and not _DOTENV_INSTALLED:
            self.logger.warning("python-dotenv is not installed. Cannot load .env file.")

        # Инициализация провайдера секретов
        self.secret_provider = secret_provider
        if secret_provider:
            self.logger.info("Using secret provider for key management")

        self.keys = parse_keys(api_keys, env_var, self.logger)
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
        self.config_loader = config_loader if config_loader else ConfigLoader(
            config_file=config_file,
            logger=self.logger
        )
        self.config = self.config_loader.load_config()
        self.error_classifier = error_classifier if error_classifier else ErrorClassifier()

        # Инициализация стратегии ротации
        self.rotation_strategy_kwargs = rotation_strategy_kwargs or {}
        self._init_rotation_strategy(rotation_strategy)

        # Инициализация middleware
        self.middlewares = middlewares if middlewares else []

        # Инициализация метрик
        self.enable_metrics = enable_metrics
        self.metrics = RotatorMetrics() if enable_metrics else None
        self._key_metrics: Dict[str, KeyStats] = {  # Изменено на KeyStats
            key: KeyStats() for key in self.keys  # Создаем KeyStats вместо KeyMetrics
        }

        self.logger.info(
            f"✅ Rotator инициализирован с {len(self.keys)} ключами. "
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
        """Инициализирует стратегию ротации"""
        if isinstance(rotation_strategy, BaseRotationStrategy):
            self.rotation_strategy = rotation_strategy
        else:
            self.rotation_strategy = create_rotation_strategy(
                rotation_strategy,
                self.keys,
                **self.rotation_strategy_kwargs
            )
        self.logger.debug(f"Rotation strategy initialized: {type(self.rotation_strategy).__name__}")

    @staticmethod
    def _get_domain_from_url(url: str) -> str:
        """Извлекает домен из URL"""
        from urllib.parse import urlparse
        parsed_url = urlparse(url)
        return parsed_url.netloc

    def get_next_key(self) -> str:
        """
        Получить следующий ключ согласно стратегии ротации.

        Returns:
            str: Следующий API ключ
        """
        # Передаем словарь KeyStats вместо KeyMetrics
        key = self.rotation_strategy.get_next_key(self._key_metrics)
        self.logger.debug(f"Selected key: {key[:8]}...")
        return key

    def get_next_user_agent(self) -> Optional[str]:
        """Получить следующий User-Agent"""
        if not self.user_agents:
            return None
        ua = self.user_agents[self.current_user_agent_index]
        self.current_user_agent_index = (self.current_user_agent_index + 1) % len(self.user_agents)
        self.logger.debug(f"Using User-Agent: {ua}")
        return ua

    def get_next_proxy(self) -> Optional[str]:
        """Получить следующий прокси"""
        if not self.proxy_list:
            return None
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
        Подготавливает заголовки и куки с авторизацией и ротацией User-Agent.

        Args:
            key: API ключ
            custom_headers: Пользовательские заголовки
            url: URL запроса

        Returns:
            Tuple[dict, dict]: Заголовки и куки
        """
        headers = custom_headers.copy() if custom_headers else {}
        cookies = {}

        domain = self._get_domain_from_url(url)

        # Применяем сохраненные заголовки для домена
        if domain in self.config.get("successful_headers", {}):
            self.logger.debug(f"Applying saved headers for domain: {domain}")
            headers.update(self.config["successful_headers"][domain])

        # Выполняем header_callback если предоставлен
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

        # Автоматическое определение заголовка авторизации
        if "Authorization" not in headers and not any(h.lower() == "authorization" for h in headers.keys()):
            if key.startswith("sk-") or key.startswith("pk-"):
                headers["Authorization"] = f"Bearer {key}"
                self.logger.debug(f"Inferred Authorization header: Bearer {key[:8]}...")
            elif len(key) == 32:
                headers["X-API-Key"] = key
                self.logger.debug(f"Inferred X-API-Key header: {key[:8]}...")
            else:
                headers["Authorization"] = f"Key {key}"
                self.logger.debug(f"Inferred Authorization header (default): Key {key[:8]}...")

        # Ротация User-Agent
        user_agent = self.get_next_user_agent()
        if user_agent and "User-Agent" not in headers and not any(h.lower() == "user-agent" for h in headers.keys()):
            headers["User-Agent"] = user_agent
            self.logger.debug(f"Added User-Agent header: {user_agent}")

        return headers, cookies

    def _apply_random_delay(self):
        """Применяет случайную задержку, если настроено"""
        if self.random_delay_range:
            delay = random.uniform(self.random_delay_range[0], self.random_delay_range[1])
            self.logger.info(f"⏳ Applying random delay of {delay:.2f} seconds.")
            time.sleep(delay)

    def reset_key_health(self, key: Optional[str] = None):
        """
        Сбрасывает статус здоровья ключа/ключей.

        Args:
            key: Конкретный ключ для сброса. Если None, сбрасывает все ключи.
        """
        if key:
            if key in self._key_metrics:
                self._key_metrics[key].is_healthy = True
                self._key_metrics[key].consecutive_failures = 0
                self.logger.info(f"Reset health for key: {key[:8]}...")
            else:
                self.logger.warning(f"Key {key[:8]}... not found in metrics")
        else:
            for k in self._key_metrics:
                self._key_metrics[k].is_healthy = True
                self._key_metrics[k].consecutive_failures = 0
            self.logger.info("Reset health for all keys")

    def get_key_statistics(self) -> Dict[str, Dict]:
        """
        Получить статистику по всем ключам.

        Returns:
            Dict: Словарь со статистикой каждого ключа
        """
        return {
            key: metrics.to_dict()
            for key, metrics in self._key_metrics.items()
        }

    def get_metrics(self) -> Optional[Dict]:
        """
        Получить общие метрики ротатора.

        Returns:
            Optional[Dict]: Метрики или None если метрики отключены
        """
        if self.metrics:
            return self.metrics.get_metrics()
        return None

    def export_config(self) -> Dict:
        """
        Экспортировать текущую конфигурацию.

        Returns:
            Dict: Текущая конфигурация
        """
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
        """Обновляет ключи из secret provider"""
        if not self.secret_provider:
            self.logger.warning("No secret provider configured")
            return

        try:
            new_keys = await self.secret_provider.refresh_keys()
            if new_keys:
                self.keys = new_keys
                self._key_metrics = {key: KeyStats() for key in self.keys}  # Изменено на KeyStats
                self._init_rotation_strategy(self.rotation_strategy)
                self.logger.info(f"Refreshed {len(new_keys)} keys from secret provider")
        except Exception as e:
            self.logger.error(f"Failed to refresh keys from provider: {e}")

    @property
    def key_count(self):
        """Количество ключей"""
        return len(self.keys)

    def __len__(self):
        return len(self.keys)

    def __repr__(self):
        return f"<{self.__class__.__name__} keys={self.key_count} retries={self.max_retries}>"


class APIKeyRotator(BaseKeyRotator):
    """
    Супер-простой в использовании, но мощный ротатор API ключей (СИНХРОННЫЙ).
    Автоматически обрабатывает лимиты, ошибки и ретраи.
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
        self.logger.info(f"✅ Sync APIKeyRotator инициализирован с Connection Pooling")

    def _should_retry(self, response: requests.Response) -> bool:
        """Определяет, нужно ли повторять запрос"""
        if self.should_retry_callback:
            return self.should_retry_callback(response)
        error_type = self.error_classifier.classify_error(response=response)
        return error_type in [ErrorType.RATE_LIMIT, ErrorType.TEMPORARY]

    async def _run_middleware_before_request(self, request_info: RequestInfo) -> RequestInfo:
        """Выполняет before_request для всех middleware"""
        for middleware in self.middlewares:
            request_info = await middleware.before_request(request_info)
        return request_info

    async def _run_middleware_after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        """Выполняет after_request для всех middleware"""
        for middleware in self.middlewares:
            response_info = await middleware.after_request(response_info)
        return response_info

    async def _run_middleware_on_error(self, error_info: ErrorInfo) -> bool:
        """Выполняет on_error для всех middleware. Возвращает True если ошибка обработана"""
        for middleware in self.middlewares:
            if await middleware.on_error(error_info):
                return True
        return False

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        Выполняет запрос. Просто как requests, но с ротацией ключей!

        Args:
            method: HTTP метод
            url: URL запроса
            **kwargs: Дополнительные параметры для requests

        Returns:
            requests.Response: Ответ сервера

        Raises:
            AllKeysExhaustedError: Если все ключи исчерпаны
        """
        self.logger.info(f"Initiating {method} request to {url} with key rotation.")

        domain = self._get_domain_from_url(url)
        start_time = time.time()

        for attempt in range(self.max_retries):
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

            # Middleware: before_request
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
                import asyncio
                request_info = asyncio.run(self._run_middleware_before_request(request_info))
                kwargs["headers"] = request_info.headers
                kwargs["cookies"] = request_info.cookies

            try:
                self.logger.debug(f"Attempt {attempt + 1}/{self.max_retries} with key {key[:8]}...")
                response_obj = self.session.request(method, url, **kwargs)
                request_time = time.time() - start_time

                self.logger.debug(f"Received response with status code: {response_obj.status_code}")

                # Middleware: after_request
                response_info = ResponseInfo(
                    status_code=response_obj.status_code,
                    headers=dict(response_obj.headers),
                    content=response_obj.content,
                    request_info=request_info
                )

                if self.middlewares:
                    import asyncio
                    response_info = asyncio.run(self._run_middleware_after_request(response_info))

                error_type = self.error_classifier.classify_error(response=response_obj)

                # Обновление метрик
                if self.metrics:
                    self.metrics.record_request(
                        key=key,
                        endpoint=url,
                        success=(error_type not in [ErrorType.RATE_LIMIT, ErrorType.TEMPORARY, ErrorType.PERMANENT]),
                        response_time=request_time,
                        is_rate_limited=(error_type == ErrorType.RATE_LIMIT)
                    )

                # Обновление метрик ключа
                self._key_metrics[key].last_used = time.time()

                if error_type == ErrorType.PERMANENT:
                    self.logger.error(
                        f"❌ Key {key[:8]}... is permanently invalid (Status: {response_obj.status_code}). Removing from rotation.")
                    self.keys.remove(key)
                    if key in self._key_metrics:
                        del self._key_metrics[key]
                    if not self.keys:
                        raise AllKeysExhaustedError("All keys are permanently invalid.")
                    continue
                elif error_type == ErrorType.RATE_LIMIT:
                    self._key_metrics[key].rate_limit_hits += 1
                    self.logger.warning(
                        f"↻ Attempt {attempt + 1}/{self.max_retries}. Key {key[:8]}... rate limited. Retrying with next key...")
                elif error_type == ErrorType.TEMPORARY:
                    self.logger.warning(
                        f"↻ Attempt {attempt + 1}/{self.max_retries}. Key {key[:8]}... temporary error. Retrying...")
                elif not self._should_retry(response_obj):
                    self.logger.info(f"✅ Request successful with key {key[:8]}... Status: {response_obj.status_code}")
                    # Сохранение успешных заголовков
                    if domain not in self.config.get("successful_headers", {}):
                        self.config.setdefault("successful_headers", {})[domain] = headers
                        self.config_loader.save_config(self.config)
                        self.logger.info(f"Saved successful headers for domain: {domain}")
                    return response_obj

                self.logger.warning(
                    f"↻ Attempt {attempt + 1}/{self.max_retries}. Key {key[:8]}... unexpected error: {response_obj.status_code}. Retrying...")

            except requests.RequestException as e:
                error_type = self.error_classifier.classify_error(exception=e)

                # Middleware: on_error
                error_info = ErrorInfo(exception=e, request_info=request_info)
                if self.middlewares:
                    import asyncio
                    handled = asyncio.run(self._run_middleware_on_error(error_info))
                    if handled:
                        self.logger.info(f"Error handled by middleware")
                        continue

                if error_type == ErrorType.NETWORK:
                    self.logger.error(
                        f"⚠️ Network error with key {key[:8]}... on attempt {attempt + 1}/{self.max_retries}: {e}. Trying next key...")
                else:
                    self.logger.error(
                        f"⚠️ Request exception with key {key[:8]}... on attempt {attempt + 1}/{self.max_retries}: {e}. Trying next key...")

            if attempt < self.max_retries - 1:
                delay = self.base_delay * (2 ** attempt)
                self.logger.info(f"Waiting for {delay:.2f} seconds before next attempt.")
                time.sleep(delay)

        self.logger.error(f"❌ All {len(self.keys)} keys exhausted after {self.max_retries} attempts each for {url}.")
        raise AllKeysExhaustedError(f"All {len(self.keys)} keys exhausted after {self.max_retries} attempts each")

    def get(self, url, **kwargs):
        """GET запрос"""
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        """POST запрос"""
        return self.request("POST", url, **kwargs)

    def put(self, url, **kwargs):
        """PUT запрос"""
        return self.request("PUT", url, **kwargs)

    def delete(self, url, **kwargs):
        """DELETE запрос"""
        return self.request("DELETE", url, **kwargs)


class AsyncAPIKeyRotator(BaseKeyRotator):
    """
    Супер-простой в использовании, но мощный ротатор API ключей (АСИНХРОННЫЙ).
    Автоматически обрабатывает лимиты, ошибки и ретраи.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._session: Optional[aiohttp.ClientSession] = None
        self.logger.info(f"✅ Async APIKeyRotator инициализирован")

    async def __aenter__(self):
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            self.logger.info("Closing aiohttp client session.")
            await self._session.close()

    async def _get_session(self) -> aiohttp.ClientSession:
        """Получает или создает сессию"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout))
            self.logger.debug("Created new aiohttp client session.")
        return self._session

    def _should_retry(self, status: int) -> bool:
        """Определяет, нужно ли повторять запрос по статусу"""
        if self.should_retry_callback:
            return self.should_retry_callback(status)
        error_type = self.error_classifier.classify_error(response=MagicMock(status_code=status))
        return error_type in [ErrorType.RATE_LIMIT, ErrorType.TEMPORARY]

    async def request(self, method: str, url: str, **kwargs) -> aiohttp.ClientResponse:
        """
        Выполняет асинхронный запрос. Просто как aiohttp, но с ротацией ключей!

        Args:
            method: HTTP метод
            url: URL запроса
            **kwargs: Дополнительные параметры для aiohttp

        Returns:
            aiohttp.ClientResponse: Ответ сервера
        """
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
                self.logger.info(f"⏳ Applying random delay of {delay:.2f} seconds.")
                await asyncio.sleep(delay)

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
            self.logger.debug(f"Performing async request with key {key[:8]}...")
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

            error_type = self.error_classifier.classify_error(response=MagicMock(status_code=response_obj.status))

            # Обновление метрик
            if self.metrics:
                self.metrics.record_request(
                    key=key,
                    endpoint=url,
                    success=(error_type not in [ErrorType.RATE_LIMIT, ErrorType.TEMPORARY, ErrorType.PERMANENT]),
                    response_time=request_time,
                    is_rate_limited=(error_type == ErrorType.RATE_LIMIT)
                )

            # Обновление метрик ключа
            self._key_metrics[key].last_used = time.time()

            if error_type == ErrorType.PERMANENT:
                self.logger.error(
                    f"❌ Key {key[:8]}... is permanently invalid (Status: {response_obj.status}). Removing from rotation.")
                self.keys.remove(key)
                if key in self._key_metrics:
                    del self._key_metrics[key]
                await response_obj.release()
                if not self.keys:
                    raise AllKeysExhaustedError("All keys are permanently invalid.")
                raise aiohttp.ClientError("Permanent key error, try next key.")
            elif error_type == ErrorType.RATE_LIMIT:
                self._key_metrics[key].rate_limit_hits += 1
                self.logger.warning(
                    f"↻ Key {key[:8]}... rate limited (Status: {response_obj.status}). Retrying with next key...")
                await response_obj.release()
                raise aiohttp.ClientError("Rate limit hit, try next key.")
            elif error_type == ErrorType.TEMPORARY:
                self.logger.warning(f"↻ Key {key[:8]}... temporary error (Status: {response_obj.status}). Retrying...")
                await response_obj.release()
                raise aiohttp.ClientError("Temporary error, retry with same key.")
            elif not self._should_retry(response_obj.status):
                self.logger.info(f"✅ Async request successful with key {key[:8]}... Status: {response_obj.status}")
                # Сохранение успешных заголовков
                if domain not in self.config.get("successful_headers", {}):
                    self.config.setdefault("successful_headers", {})[domain] = headers
                    self.config_loader.save_config(self.config)
                    self.logger.info(f"Saved successful headers for domain: {domain}")
                return response_obj

            self.logger.warning(f"↻ Key {key[:8]}... unexpected error: {response_obj.status}. Retrying...")
            await response_obj.release()
            raise aiohttp.ClientError("Unexpected error, retry.")

        # Выполнение с retry
        final_response = await async_retry_with_backoff(
            _perform_single_request_with_key_coroutine,
            retries=len(self.keys) * self.max_retries,
            backoff_factor=self.base_delay,
            exceptions=aiohttp.ClientError
        )

        return final_response

    async def get(self, url, **kwargs) -> aiohttp.ClientResponse:
        """GET запрос"""
        return await self.request("GET", url, **kwargs)

    async def post(self, url, **kwargs) -> aiohttp.ClientResponse:
        """POST запрос"""
        return await self.request("POST", url, **kwargs)

    async def put(self, url, **kwargs) -> aiohttp.ClientResponse:
        """PUT запрос"""
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url, **kwargs) -> aiohttp.ClientResponse:
        """DELETE запрос"""
        return await self.request("DELETE", url, **kwargs)