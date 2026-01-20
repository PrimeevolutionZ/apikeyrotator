"""
Middleware for retry logic
"""

import asyncio
import time
import logging
import threading
from typing import Dict, Any, Optional
from collections import OrderedDict
from .base import RotatorMiddleware
from .models import RequestInfo, ResponseInfo, ErrorInfo


class RetryMiddleware(RotatorMiddleware):
    """
    Middleware для обработки повторных попыток запросов.

    Отслеживает количество попыток для каждого URL и применяет
    экспоненциальную задержку между попытками.
    """

    def __init__(
            self,
            max_retries: int = 3,
            backoff_factor: float = 1.0,
            max_tracked_urls: int = 1000,
            logger: Optional[logging.Logger] = None
    ):
        """
        Args:
            max_retries: Максимальное количество повторных попыток
            backoff_factor: Базовая задержка для экспоненциального роста
            max_tracked_urls: Максимальное количество отслеживаемых URL
            logger: Логгер для вывода сообщений
        """
        self.max_retries = max_retries
        self.backoff_factor = max(0.0, backoff_factor)  # Ensure non-negative
        self.max_tracked_urls = max(1, max_tracked_urls)

        self.logger = logger if logger else logging.getLogger(__name__)

        # Отслеживание количества попыток по URL (LRU)
        self.retry_counts: OrderedDict[str, int] = OrderedDict()

        # Thread-safety
        self._lock = threading.RLock()

        self.logger.info(
            f"RetryMiddleware initialized: max_retries={max_retries}, "
            f"backoff_factor={backoff_factor}, max_tracked_urls={max_tracked_urls}"
        )

    def _evict_oldest(self):
        """Удалить самую старую запись при превышении лимита"""
        with self._lock:
            if len(self.retry_counts) >= self.max_tracked_urls:
                # Удалить 10% самых старых, но минимум 1
                to_remove = max(1, len(self.retry_counts) // 10)
                for _ in range(to_remove):
                    if self.retry_counts:
                        self.retry_counts.popitem(last=False)
                self.logger.debug(f"Evicted {to_remove} oldest retry entries")

    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        """
        Проверяет количество попыток перед запросом (не блокирует).

        Args:
            request_info: Информация о запросе

        Returns:
            RequestInfo: Неизменённая информация о запросе
        """
        # Просто пропускаем запрос без изменений
        return request_info

    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        """
        Обрабатывает успешный ответ - сбрасывает счётчик попыток.

        Args:
            response_info: Информация об ответе

        Returns:
            ResponseInfo: Неизменённая информация об ответе
        """
        url = response_info.request_info.url

        # Если запрос успешен (2xx), удаляем URL из отслеживания
        if 200 <= response_info.status_code < 300:
            with self._lock:
                if url in self.retry_counts:
                    del self.retry_counts[url]
                    self.logger.debug(f"Removed {url} from retry tracking (success)")

        return response_info

    async def on_error(self, error_info: ErrorInfo) -> bool:
        """
        Обрабатывает ошибку - увеличивает счётчик и применяет задержку.

        Args:
            error_info: Информация об ошибке

        Returns:
            bool: True если нужно повторить запрос, False если исчерпаны попытки
        """
        url = error_info.request_info.url

        with self._lock:
            # Проверяем лимит перед добавлением
            if url not in self.retry_counts:
                self._evict_oldest()

            # Увеличиваем счётчик попыток
            current_retry = self.retry_counts.get(url, 0)
            self.retry_counts[url] = current_retry + 1
            self.retry_counts.move_to_end(url)  # LRU

            retry_count = self.retry_counts[url]

        # Проверяем лимит попыток
        if retry_count > self.max_retries:
            self.logger.warning(
                f"❌ Max retries ({self.max_retries}) exceeded for {url}"
            )
            with self._lock:
                # Очищаем после исчерпания попыток
                if url in self.retry_counts:
                    del self.retry_counts[url]
            return False

        # Вычисляем задержку с экспоненциальным ростом
        # delay = backoff_factor * (2 ^ (retry_count - 1))
        if self.backoff_factor > 0:
            delay = self.backoff_factor * (2 ** (retry_count - 1))

            self.logger.info(
                f"🔄 Retry {retry_count}/{self.max_retries} for {url} "
                f"after {delay:.2f}s delay"
            )

            # Применяем задержку
            await asyncio.sleep(delay)
        else:
            self.logger.info(
                f"🔄 Retry {retry_count}/{self.max_retries} for {url} "
                f"(no delay, backoff_factor=0)"
            )

        return True
