import os
import time
import requests
import asyncio
import aiohttp
import logging
from typing import List, Optional, Dict, Union, Callable, Awaitable
from .exceptions import NoAPIKeysError, AllKeysExhaustedError
from .utils import async_retry_with_backoff

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class BaseKeyRotator:
    """
    Базовый класс для общей логики ротации ключей.
    """
    def __init__(
            self,
            api_keys: Optional[Union[List[str], str]] = None,
            env_var: str = "API_KEYS",
            max_retries: int = 3,
            base_delay: float = 1.0,
            timeout: float = 10.0,
            should_retry_callback: Optional[Callable[[Union[requests.Response, int]], bool]] = None,
            header_callback: Optional[Callable[[str, Optional[dict]], dict]] = None
    ):
        self.keys = self._parse_keys(api_keys, env_var)
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.timeout = timeout
        self.current_index = 0
        self.should_retry_callback = should_retry_callback
        self.header_callback = header_callback
        logger.info(f"✅ Rotator инициализирован с {len(self.keys)} ключами")

    def _parse_keys(self, api_keys, env_var) -> List[str]:
        """Умный парсинг ключей из разных источников с понятными ошибками"""
        if api_keys is not None:
            if isinstance(api_keys, str):
                keys = [k.strip() for k in api_keys.split(",") if k.strip()]
            elif isinstance(api_keys, list):
                keys = api_keys
            else:
                raise NoAPIKeysError("❌ API keys must be a list or comma-separated string")

            if not keys:
                raise NoAPIKeysError("❌ No API keys provided in the api_keys parameter")

            return keys

        keys_str = os.getenv(env_var)

        if keys_str is None:
            raise NoAPIKeysError(
                f"❌ No API keys found.\n"
                f"   Please either:\n"
                f"   1. Pass keys directly: APIKeyRotator(api_keys=[\"key1\", \"key2\"])\n"
                f"   2. Set environment variable: export {env_var}=\'key1,key2\'\n"
                f"   3. Create .env file with: {env_var}=key1,2\n"
            )

        if not keys_str.strip():
            raise NoAPIKeysError(
                f"❌ Environment variable ${env_var} is empty.\n"
                f"   Please set it with: export {env_var}=\'your_key1,your_key2\'"
            )

        keys = [k.strip() for k in keys_str.split(",") if k.strip()]

        if not keys:
            raise NoAPIKeysError(
                f"❌ No valid API keys found in ${env_var}.\n"
                f"   Format should be: key1,key2,key3\n"
                f"   Current value: \'{keys_str}\'"
            )

        return keys

    def get_next_key(self) -> str:
        """Получить следующий ключ"""
        key = self.keys[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.keys)
        return key

    def _prepare_headers(self, key: str, custom_headers: Optional[dict]) -> dict:
        """Подготавливает заголовки с авторизацией"""
        if self.header_callback:
            return self.header_callback(key, custom_headers)

        headers = custom_headers.copy() if custom_headers else {}

        if "Authorization" not in headers:
            if key.startswith("sk-") or key.startswith("pk-"):  # OpenAI style
                headers["Authorization"] = f"Bearer {key}"
            elif len(key) == 32:  # API key style (e.g., some custom APIs)
                headers["X-API-Key"] = key
            else:  # Default fallback
                headers["Authorization"] = f"Key {key}"

        return headers

    @property
    def key_count(self):
        return len(self.keys)

    def __len__(self):
        return len(self.keys)

    def __repr__(self):
        return f"<BaseKeyRotator keys={self.key_count} retries={self.max_retries}>"


class APIKeyRotator(BaseKeyRotator):
    """
    Супер-простой в использовании, но мощный ротатор API ключей (СИНХРОННЫЙ).
    Автоматически обрабатывает лимиты, ошибки и ретраи.
    """

    def __init__(
            self,
            api_keys: Optional[Union[List[str], str]] = None,
            env_var: str = "API_KEYS",
            max_retries: int = 3,
            base_delay: float = 1.0,
            timeout: float = 10.0,
            should_retry_callback: Optional[Callable[[requests.Response], bool]] = None,
            header_callback: Optional[Callable[[str, Optional[dict]], dict]] = None
    ):
        super().__init__(api_keys, env_var, max_retries, base_delay, timeout, should_retry_callback, header_callback)
        self.session = requests.Session()
        logger.info(f"✅ Sync APIKeyRotator инициализирован с {len(self.keys)} ключами")

    def _should_retry(self, response: requests.Response) -> bool:
        """Определяет, нужно ли повторять запрос"""
        if self.should_retry_callback:
            return self.should_retry_callback(response)
        return response.status_code in [429, 500, 502, 503, 504]

    def request(
            self,
            method: str,
            url: str,
            **kwargs
    ) -> requests.Response:
        """
        Выполняет запрос. Просто как requests, но с ротацией ключей!
        """

        for attempt in range(self.max_retries):
            key = self.get_next_key()
            headers = self._prepare_headers(key, kwargs.get("headers"))
            kwargs["headers"] = headers
            kwargs["timeout"] = kwargs.get("timeout", self.timeout)

            try:
                response = self.session.request(method, url, **kwargs)

                if not self._should_retry(response):
                    return response

                logger.warning(f"↻ Attempt {attempt + 1}/{self.max_retries}. Key {key[:8]}... rate limited or error: {response.status_code}")

            except requests.RequestException as e:
                logger.error(f"⚠️ Network error with key {key[:8]}...: {e}. Trying next key...")

            if attempt < self.max_retries - 1:
                delay = self.base_delay * (2 ** attempt)
                time.sleep(delay)

        raise AllKeysExhaustedError(f"All {len(self.keys)} keys exhausted after {self.max_retries} attempts")

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    def put(self, url, **kwargs):
        return self.request("PUT", url, **kwargs)

    def delete(self, url, **kwargs):
        return self.request("DELETE", url, **kwargs)


class AsyncAPIKeyRotator(BaseKeyRotator):
    """
    Супер-простой в использовании, но мощный ротатор API ключей (АСИНХРОННЫЙ).
    Автоматически обрабатывает лимиты, ошибки и ретраи.
    """

    def __init__(
            self,
            api_keys: Optional[Union[List[str], str]] = None,
            env_var: str = "API_KEYS",
            max_retries: int = 3,
            base_delay: float = 1.0,
            timeout: float = 10.0,
            should_retry_callback: Optional[Callable[[int], bool]] = None,
            header_callback: Optional[Callable[[str, Optional[dict]], dict]] = None
    ):
        super().__init__(api_keys, env_var, max_retries, base_delay, timeout, should_retry_callback, header_callback)
        self._session: Optional[aiohttp.ClientSession] = None
        logger.info(f"✅ Async APIKeyRotator инициализирован с {len(self.keys)} ключами")

    async def __aenter__(self):
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout))
        return self._session

    def _should_retry(self, status: int) -> bool:
        """Определяет, нужно ли повторять запрос по статусу"""
        if self.should_retry_callback:
            return self.should_retry_callback(status)
        return status in [429, 500, 502, 503, 504]

    async def request(
            self,
            method: str,
            url: str,
            **kwargs
    ) -> aiohttp.ClientResponse:
        """
        Выполняет асинхронный запрос. Просто как aiohttp, но с ротацией ключей!
        """
        session = await self._get_session()

        for _ in range(len(self.keys)):
            key = self.get_next_key()
            headers = self._prepare_headers(key, kwargs.get("headers"))
            kwargs["headers"] = headers

            async def _perform_single_request_with_key():
                async with session.request(method, url, **kwargs) as response:
                    if self._should_retry(response.status):
                        logger.warning(f"↻ Key {key[:8]}... returned status {response.status}. Retrying with same key...")
                        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
                    return response

            try:
                return await async_retry_with_backoff(
                    _perform_single_request_with_key,
                    retries=self.max_retries, # Max retries for this specific key
                    backoff_factor=self.base_delay,
                    exceptions=aiohttp.ClientError
                )
            except aiohttp.ClientError as e:
                logger.error(f"⚠️ All retries failed for key {key[:8]}...: {e}. Trying next key...")
                # Continue to the next key in the outer loop

        raise AllKeysExhaustedError(f"All {self.key_count} keys exhausted after {self.max_retries} attempts each")

    async def get(self, url, **kwargs) -> aiohttp.ClientResponse:
        return await self.request("GET", url, **kwargs)

    async def post(self, url, **kwargs) -> aiohttp.ClientResponse:
        return await self.request("POST", url, **kwargs)

    async def put(self, url, **kwargs) -> aiohttp.ClientResponse:
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url, **kwargs) -> aiohttp.ClientResponse:
        return await self.request("DELETE", url, **kwargs)

    def __repr__(self):
        return f"<AsyncAPIKeyRotator keys={self.key_count} retries={self.max_retries}>"

