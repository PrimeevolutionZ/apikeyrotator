import os
import time
import requests
from typing import List, Optional, Dict, Union, Callable
from .exceptions import NoAPIKeysError, AllKeysExhaustedError


class APIKeyRotator:
    """
    Супер-простой в использовании, но мощный ротатор API ключей.
    Автоматически обрабатывает лимиты, ошибки и ретраи.
    """

    def __init__(
            self,
            api_keys: Optional[Union[List[str], str]] = None,
            env_var: str = "API_KEYS",
            max_retries: int = 3,
            base_delay: float = 1.0
    ):
        """
        Простая инициализация - передай ключи или используй переменные окружения

        :param api_keys: Список ключей или строка с ключами через запятую
        :param env_var: Имя переменной окружения
        :param max_retries: Максимальное количество попыток
        :param base_delay: Базовая задержка между попытками
        """
        self.keys = self._parse_keys(api_keys, env_var)
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.current_index = 0
        self.session = requests.Session()
        print(f"✅ APIKeyRotator инициализирован с {len(self.keys)} ключами")

    def _parse_keys(self, api_keys, env_var) -> List[str]:
        """Умный парсинг ключей из разных источников с понятными ошибками"""
        # Если ключи переданы напрямую
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

        # Если ключи ищем в переменных окружения
        keys_str = os.getenv(env_var)

        if keys_str is None:
            raise NoAPIKeysError(
                f"❌ No API keys found.\n"
                f"   Please either:\n"
                f"   1. Pass keys directly: APIKeyRotator(api_keys=['key1', 'key2'])\n"
                f"   2. Set environment variable: export {env_var}='key1,key2'\n"
                f"   3. Create .env file with: {env_var}=key1,key2"
            )

        if not keys_str.strip():
            raise NoAPIKeysError(
                f"❌ Environment variable ${env_var} is empty.\n"
                f"   Please set it with: export {env_var}='your_key1,your_key2'"
            )

        keys = [k.strip() for k in keys_str.split(",") if k.strip()]

        if not keys:
            raise NoAPIKeysError(
                f"❌ No valid API keys found in ${env_var}.\n"
                f"   Format should be: key1,key2,key3\n"
                f"   Current value: '{keys_str}'"
            )

        return keys

    def get_next_key(self) -> str:
        """Получить следующий ключ"""
        key = self.keys[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.keys)
        return key

    def _should_retry(self, response: requests.Response) -> bool:
        """Определяет, нужно ли повторять запрос"""
        return response.status_code in [429, 500, 502, 503, 504]

    def _prepare_headers(self, key: str, custom_headers: dict) -> dict:
        """Подготавливает заголовки с авторизацией"""
        headers = custom_headers.copy() if custom_headers else {}

        # Автоматически определяем тип авторизации
        if "Authorization" not in headers:
            if key.startswith("sk-") or key.startswith("pk-"):  # OpenAI style
                headers["Authorization"] = f"Bearer {key}"
            elif len(key) == 32:  # API key style
                headers["X-API-Key"] = key
            else:  # Default
                headers["Authorization"] = f"Key {key}"

        return headers

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

            # Автоматически готовим заголовки
            kwargs['headers'] = self._prepare_headers(key, kwargs.get('headers', {}))

            try:
                response = self.session.request(method, url, **kwargs)

                if not self._should_retry(response):
                    return response

                print(f"↻ Attempt {attempt + 1}/{self.max_retries}. Key {key[:8]}... rate limited")

            except requests.RequestException as e:
                print(f"⚠️ Network error: {e}. Trying next key...")

            # Экспоненциальная задержка
            if attempt < self.max_retries - 1:
                delay = self.base_delay * (2 ** attempt)
                time.sleep(delay)

        raise AllKeysExhaustedError(f"All {len(self.keys)} keys exhausted after {self.max_retries} attempts")

    # Простейшие методы-обертки
    def get(self, url, **kwargs):
        return self.request('GET', url, **kwargs)

    def post(self, url, **kwargs):
        return self.request('POST', url, **kwargs)

    def put(self, url, **kwargs):
        return self.request('PUT', url, **kwargs)

    def delete(self, url, **kwargs):
        return self.request('DELETE', url, **kwargs)

    # Удобные свойства
    @property
    def key_count(self):
        return len(self.keys)

    def __len__(self):
        return len(self.keys)

    def __repr__(self):
        return f"<APIKeyRotator keys={self.key_count} retries={self.max_retries}>"