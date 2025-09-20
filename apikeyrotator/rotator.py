
import os
import time
import requests
import asyncio
import aiohttp
import logging
import random
import json
from typing import List, Optional, Dict, Union, Callable, Awaitable, Tuple
from .exceptions import NoAPIKeysError, AllKeysExhaustedError
from .utils import async_retry_with_backoff

try:
    from dotenv import load_dotenv
    _DOTENV_INSTALLED = True
except ImportError:
    _DOTENV_INSTALLED = False

# Настройка логирования по умолчанию
def _setup_default_logger():
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
    ):
        self.logger = logger if logger else _setup_default_logger()

        if load_env_file and _DOTENV_INSTALLED:
            self.logger.debug("Attempting to load .env file.")
            load_dotenv()

        self.keys = self._parse_keys(api_keys, env_var)
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.timeout = timeout
        self.current_index = 0
        self.should_retry_callback = should_retry_callback
        self.header_callback = header_callback
        self.user_agents = user_agents if user_agents else []
        self.current_user_agent_index = 0
        self.random_delay_range = random_delay_range
        self.proxy_list = proxy_list if proxy_list else []
        self.current_proxy_index = 0
        self.config_file = config_file
        self.config = self._load_config()
        self.logger.info(f"✅ Rotator инициализирован с {len(self.keys)} ключами. Max retries: {self.max_retries}, Base delay: {self.base_delay}s, Timeout: {self.timeout}s")
        if self.user_agents: self.logger.info(f"User-Agent rotation enabled with {len(self.user_agents)} agents.")
        if self.random_delay_range: self.logger.info(f"Random delay enabled: {self.random_delay_range[0]}s - {self.random_delay_range[1]}s.")
        if self.proxy_list: self.logger.info(f"Proxy rotation enabled with {len(self.proxy_list)} proxies.")

    def _load_config(self) -> dict:
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r') as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    self.logger.warning(f"Could not decode JSON from {self.config_file}. Starting with empty config.")
                    return {}
        return {}

    def _save_config(self):
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=4)

    def _get_domain_from_url(self, url: str) -> str:
        from urllib.parse import urlparse
        parsed_url = urlparse(url)
        return parsed_url.netloc

    def _parse_keys(self, api_keys, env_var) -> List[str]:
        """Умный парсинг ключей из разных источников с понятными ошибками"""
        if api_keys is not None:
            if isinstance(api_keys, str):
                keys = [k.strip() for k in api_keys.split(",") if k.strip()]
            elif isinstance(api_keys, list):
                keys = api_keys
            else:
                self.logger.error("❌ API keys must be a list or comma-separated string.")
                raise NoAPIKeysError("❌ API keys must be a list or comma-separated string")

            if not keys:
                self.logger.error("❌ No API keys provided in the api_keys parameter.")
                raise NoAPIKeysError("❌ No API keys provided in the api_keys parameter")

            return keys

        keys_str = os.getenv(env_var)

        if keys_str is None:
            error_msg = (
                f"❌ No API keys found.\n"
                f"   Please either:\n"
                f"   1. Pass keys directly: APIKeyRotator(api_keys=[\"key1\", \"key2\"])\n"
                f"   2. Set environment variable: export {env_var}=\'key1,key2\'\n"
                f"   3. Create .env file with: {env_var}=key1,2\n"
            )
            self.logger.error(error_msg)
            raise NoAPIKeysError(error_msg)

        if not keys_str.strip():
            error_msg = (
                f"❌ Environment variable ${env_var} is empty.\n"
                f"   Please set it with: export {env_var}=\'your_key1,your_key2\'"
            )
            self.logger.error(error_msg)
            raise NoAPIKeysError(error_msg)

        keys = [k.strip() for k in keys_str.split(",") if k.strip()]

        if not keys:
            error_msg = (
                f"❌ No valid API keys found in ${env_var}.\n"
                f"   Format should be: key1,key2,key3\n"
                f"   Current value: \'{keys_str}\'"
            )
            self.logger.error(error_msg)
            raise NoAPIKeysError(error_msg)

        return keys

    def get_next_key(self) -> str:
        """Получить следующий ключ"""
        key = self.keys[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.keys)
        self.logger.debug(f"Using key at index {self.current_index - 1} (next will be {self.current_index}). Key: {key[:8]}...")
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

    def _prepare_headers_and_cookies(self, key: str, custom_headers: Optional[dict], url: str) -> Tuple[dict, dict]:
        """Подготавливает заголовки и куки с авторизацией и ротацией User-Agent"""
        headers = custom_headers.copy() if custom_headers else {}
        cookies = {}

        domain = self._get_domain_from_url(url)
        if domain in self.config.get("successful_headers", {}):
            self.logger.debug(f"Applying saved headers for domain: {domain}")
            headers.update(self.config["successful_headers"][domain])

        if self.header_callback:
            self.logger.debug("Executing header_callback.")
            result = self.header_callback(key, custom_headers)
            if isinstance(result, tuple) and len(result) == 2:
                headers.update(result[0])
                cookies.update(result[1])
                self.logger.debug(f"header_callback returned headers: {result[0]} and cookies: {result[1]}")
            elif isinstance(result, dict):
                headers.update(result)
                self.logger.debug(f"header_callback returned headers: {result}")
            else:
                self.logger.warning("header_callback returned an unexpected type. Expected dict or (dict, dict).")

        if "Authorization" not in headers and not any(h.lower() == "authorization" for h in headers.keys()):
            if key.startswith("sk-") or key.startswith("pk-"):  # OpenAI style
                headers["Authorization"] = f"Bearer {key}"
                self.logger.debug(f"Inferred Authorization header: Bearer {key[:8]}...")
            elif len(key) == 32:  # API key style (e.g., some custom APIs)
                headers["X-API-Key"] = key
                self.logger.debug(f"Inferred X-API-Key header: {key[:8]}...")
            else:  # Default fallback
                headers["Authorization"] = f"Key {key}"
                self.logger.debug(f"Inferred Authorization header (default): Key {key[:8]}...")

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
            header_callback: Optional[Callable[[str, Optional[dict]], Union[dict, Tuple[dict, dict]]]] = None,
            user_agents: Optional[List[str]] = None,
            random_delay_range: Optional[Tuple[float, float]] = None,
            proxy_list: Optional[List[str]] = None,
            logger: Optional[logging.Logger] = None,
            config_file: str = "rotator_config.json",
            load_env_file: bool = True,
    ):
        super().__init__(api_keys, env_var, max_retries, base_delay, timeout, should_retry_callback, header_callback, user_agents, random_delay_range, proxy_list, logger, config_file, load_env_file)
        self.session = requests.Session()
        self.logger.info(f"✅ Sync APIKeyRotator инициализирован с {len(self.keys)} ключами")

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
        self.logger.info(f"Initiating {method} request to {url} with key rotation.")

        domain = self._get_domain_from_url(url)

        for attempt in range(self.max_retries):
            key = self.get_next_key()
            headers, cookies = self._prepare_headers_and_cookies(key, kwargs.get("headers"), url)
            kwargs["headers"] = headers
            kwargs["cookies"] = cookies # Add cookies to kwargs
            kwargs["timeout"] = kwargs.get("timeout", self.timeout)

            proxy = self.get_next_proxy()
            if proxy:
                kwargs["proxies"] = {"http": proxy, "https": proxy}
                self.logger.info(f"🌐 Using proxy: {proxy} for attempt {attempt + 1}/{self.max_retries}.")

            self._apply_random_delay()

            try:
                self.logger.debug(f"Attempt {attempt + 1}/{self.max_retries} with key {key[:8]}... and headers: {headers}")
                response = self.session.request(method, url, **kwargs)
                self.logger.debug(f"Received response with status code: {response.status_code}")

                if not self._should_retry(response):
                    self.logger.info(f"✅ Request successful with key {key[:8]}... Status: {response.status_code}")
                    # Save successful headers for this domain
                    if domain not in self.config.get("successful_headers", {}):
                        self.config.setdefault("successful_headers", {})[domain] = headers
                        self._save_config()
                        self.logger.info(f"Saved successful headers for domain: {domain}")
                    return response

                self.logger.warning(f"↻ Attempt {attempt + 1}/{self.max_retries}. Key {key[:8]}... rate limited or error: {response.status_code}. Retrying...")

            except requests.RequestException as e:
                self.logger.error(f"⚠️ Network error with key {key[:8]}... on attempt {attempt + 1}/{self.max_retries}: {e}. Trying next key or retrying...")

            if attempt < self.max_retries - 1:
                delay = self.base_delay * (2 ** attempt)
                self.logger.info(f"Waiting for {delay:.2f} seconds before next attempt.")
                time.sleep(delay)

        self.logger.error(f"❌ All {len(self.keys)} keys exhausted after {self.max_retries} attempts each for {url}.")
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
            header_callback: Optional[Callable[[str, Optional[dict]], Union[dict, Tuple[dict, dict]]]] = None,
            user_agents: Optional[List[str]] = None,
            random_delay_range: Optional[Tuple[float, float]] = None,
            proxy_list: Optional[List[str]] = None,
            logger: Optional[logging.Logger] = None,
            config_file: str = "rotator_config.json",
            load_env_file: bool = True,
    ):
        super().__init__(api_keys, env_var, max_retries, base_delay, timeout, should_retry_callback, header_callback, user_agents, random_delay_range, proxy_list, logger, config_file, load_env_file)
        self._session: Optional[aiohttp.ClientSession] = None
        self.logger.info(f"✅ Async APIKeyRotator инициализирован с {len(self.keys)} ключами")

    async def __aenter__(self):
        # Pass timeout to ClientTimeout for aiohttp session
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            self.logger.info("Closing aiohttp client session.")
            await self._session.close()

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            # Pass timeout to ClientTimeout for aiohttp session
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout))
            self.logger.debug("Created new aiohttp client session.")
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
        self.logger.info(f"Initiating async {method} request to {url} with key rotation.")
        session = await self._get_session()

        domain = self._get_domain_from_url(url)

        for _ in range(len(self.keys)):
            key = self.get_next_key()
            headers, cookies = self._prepare_headers_and_cookies(key, kwargs.get("headers"), url)
            kwargs["headers"] = headers
            kwargs["cookies"] = cookies # Add cookies to kwargs

            proxy = self.get_next_proxy()
            if proxy:
                kwargs["proxy"] = proxy
                self.logger.info(f"🌐 Using proxy: {proxy} for current request.")

            if self.random_delay_range:
                delay = random.uniform(self.random_delay_range[0], self.random_delay_range[1])
                self.logger.info(f"⏳ Applying random delay of {delay:.2f} seconds.")
                await asyncio.sleep(delay)

            async def _perform_single_request_with_key():
                self.logger.debug(f"Performing async request with key {key[:8]}... and headers: {headers}")
                async with session.request(method, url, **kwargs) as response:
                    self.logger.debug(f"Received async response with status code: {response.status}")
                    if self._should_retry(response.status):
                        self.logger.warning(f"↻ Key {key[:8]}... returned status {response.status}. Retrying with same key...")
                        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
                    return response

            try:
                response = await async_retry_with_backoff(
                    _perform_single_request_with_key,
                    retries=self.max_retries, # Max retries for this specific key
                    backoff_factor=self.base_delay,
                    exceptions=aiohttp.ClientError
                )
                self.logger.info(f"✅ Async request successful with key {key[:8]}... Status: {response.status}")
                # Save successful headers for this domain
                if domain not in self.config.get("successful_headers", {}):
                    self.config.setdefault("successful_headers", {})[domain] = headers
                    self._save_config()
                    self.logger.info(f"Saved successful headers for domain: {domain}")
                return response
            except aiohttp.ClientError as e:
                self.logger.error(f"⚠️ All retries failed for key {key[:8]}...: {e}. Trying next key...")
                # Continue to the next key in the outer loop

        self.logger.error(f"❌ All {self.key_count} keys exhausted after {self.max_retries} attempts each for {url}.")
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


