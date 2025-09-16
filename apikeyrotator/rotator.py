import os
import time
from typing import List, Optional, Callable, Any, Dict
import requests
from dotenv import load_dotenv

from .exceptions import NoAPIKeysError, APIKeyExhaustedError
# from .utils import retry_with_backoff  # можно раскомментировать позже

load_dotenv()


class APIKeyRotator:
    """
    Класс для автоматического переключения между API-ключами при достижении лимитов.
    Поддерживает round-robin ротацию и автоматический retry при ошибке 429.
    """

    def __init__(self, env_var: str = "API_KEYS", delimiter: str = ","):
        """
        Инициализация ротатора API-ключей.

        :param env_var: Имя переменной окружения, содержащей ключи (по умолчанию "API_KEYS")
        :param delimiter: Разделитель ключей в переменной окружения (по умолчанию ",")
        :raises NoAPIKeysError: Если не найдено ни одного ключа
        """
        keys_str = os.getenv(env_var, "")
        self.keys: List[str] = [k.strip() for k in keys_str.split(delimiter) if k.strip()]
        if not self.keys:
            raise NoAPIKeysError(f"No API keys found in environment variable '{env_var}'")

        self._current_index = 0
        self._usage_stats = {key: 0 for key in self.keys}  # Опционально: статистика использования

    def get_next_key(self) -> str:
        """
        Возвращает следующий API-ключ по кругу (round-robin).
        Обновляет статистику использования.

        :return: Следующий API-ключ
        """
        key = self.keys[self._current_index]
        self._current_index = (self._current_index + 1) % len(self.keys)
        self._usage_stats[key] += 1
        return key

    def get_usage_stats(self) -> Dict[str, int]:
        """
        Возвращает статистику использования ключей.

        :return: Словарь {ключ: количество использований}
        """
        return self._usage_stats.copy()

    def request_with_rotation(
        self,
        method: str,
        url: str,
        headers_fn: Callable[[str], dict],
        max_retries: Optional[int] = None,
        retry_status_codes: List[int] = None,
        **kwargs
    ) -> requests.Response:
        """
        Выполняет HTTP-запрос с автоматической ротацией API-ключей при ошибках.

        :param method: HTTP-метод ('GET', 'POST' и т.д.)
        :param url: URL для запроса
        :param headers_fn: Функция, которая принимает API-ключ и возвращает словарь заголовков
        :param max_retries: Максимальное количество попыток (по умолчанию = количество ключей)
        :param retry_status_codes: Список статус-кодов, при которых нужно сменить ключ (по умолчанию [429])
        :param kwargs: Дополнительные аргументы для requests.request (json, params, timeout и т.д.)
        :return: Ответ requests.Response
        :raises APIKeyExhaustedError: Если все попытки провалились
        :raises requests.RequestException: Если произошла сетевая ошибка и нет доступных ключей для повтора
        """
        if max_retries is None:
            max_retries = len(self.keys)

        if retry_status_codes is None:
            retry_status_codes = [429]  # По умолчанию только rate limit

        tried_keys = set()
        attempts = 0

        while attempts < max_retries:
            key = self.get_next_key()
            if key in tried_keys:
                break  # Все ключи уже перепробованы
            tried_keys.add(key)

            headers = headers_fn(key)
            try:
                response = requests.request(method, url, headers=headers, **kwargs)

                # Если статус не требует смены ключа — возвращаем ответ
                if response.status_code not in retry_status_codes:
                    return response

                # Иначе — логируем и пробуем следующий ключ
                print(f"[APIKeyRotator] Key '{key[:8]}...' returned {response.status_code}. Rotating...")

            except requests.RequestException as e:
                print(f"[APIKeyRotator] Network error with key '{key[:8]}...': {e}")

            attempts += 1

        raise APIKeyExhaustedError(
            f"All {len(tried_keys)} API keys exhausted after {attempts} attempts. Request failed."
        )

    def __repr__(self):
        return f"<APIKeyRotator keys={len(self.keys)} current_index={self._current_index}>"