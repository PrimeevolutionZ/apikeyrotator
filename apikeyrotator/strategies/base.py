"""
Базовые классы для стратегий ротации ключей
"""

from enum import Enum
from typing import List, Dict, Any, Optional, Union
from abc import ABC, abstractmethod
import time


class RotationStrategy(Enum):
    """Перечисление доступных стратегий ротации"""
    ROUND_ROBIN = "round_robin"
    RANDOM = "random"
    WEIGHTED = "weighted"
    LRU = "lru"
    FAILOVER = "failover"
    HEALTH_BASED = "health_based"
    RATE_LIMIT_AWARE = "rate_limit_aware"


class KeyMetrics:
    """
    Метрики для одного API ключа.

    Отслеживает все важные показатели производительности и здоровья ключа.
    """

    def __init__(self, key: str):
        self.key = key
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.avg_response_time = 0.0
        self.last_used = 0.0
        self.last_success = 0.0
        self.last_failure = 0.0
        self.consecutive_failures = 0
        self.rate_limit_hits = 0
        self.is_healthy = True
        # Дополнительные поля для совместимости
        self.success_rate = 1.0
        self.rate_limit_reset = 0.0
        self.requests_remaining = float('inf')

    def to_dict(self) -> Dict[str, Any]:
        """Сериализация метрик в словарь"""
        return {
            "key": self.key,
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "avg_response_time": self.avg_response_time,
            "last_used": self.last_used,
            "last_success": self.last_success,
            "last_failure": self.last_failure,
            "consecutive_failures": self.consecutive_failures,
            "rate_limit_hits": self.rate_limit_hits,
            "is_healthy": self.is_healthy,
            "success_rate": self.success_rate,
            "rate_limit_reset": self.rate_limit_reset,
            "requests_remaining": self.requests_remaining,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'KeyMetrics':
        """Десериализация метрик из словаря"""
        metrics = KeyMetrics(data["key"])
        for field, value in data.items():
            if hasattr(metrics, field):
                setattr(metrics, field, value)
        return metrics

    def update_from_request(self, success: bool, response_time: float = 0.0, **kwargs):
        """
        Обновляет метрики на основе результата запроса.

        Args:
            success: Успешность запроса
            response_time: Время выполнения запроса в секундах
            **kwargs: Дополнительные параметры (rate_limit_reset, requests_remaining, etc.)
        """
        self.total_requests += 1
        self.last_used = time.time()

        if success:
            self.successful_requests += 1
            self.last_success = time.time()
            self.consecutive_failures = 0
            # Экспоненциальное скользящее среднее для success_rate
            self.success_rate = (self.success_rate * 0.9) + (1.0 * 0.1)
        else:
            self.failed_requests += 1
            self.last_failure = time.time()
            self.consecutive_failures += 1
            self.success_rate = (self.success_rate * 0.9) + (0.0 * 0.1)

        # Обновляем среднее время ответа
        if self.total_requests > 0:
            self.avg_response_time = (
                                             self.avg_response_time * (self.total_requests - 1) + response_time
                                     ) / self.total_requests

        # Дополнительные параметры из ответа API
        if 'rate_limit_reset' in kwargs:
            self.rate_limit_reset = kwargs['rate_limit_reset']
        if 'requests_remaining' in kwargs:
            self.requests_remaining = kwargs['requests_remaining']
        if kwargs.get('is_rate_limited', False):
            self.rate_limit_hits += 1


class BaseRotationStrategy(ABC):
    """
    Базовый абстрактный класс для всех стратегий ротации.

    Все кастомные стратегии должны наследоваться от этого класса
    и реализовывать метод get_next_key().
    """

    def __init__(self, keys: Union[List[str], Dict[str, float]]):
        """
        Args:
            keys: Список ключей или словарь {ключ: вес} для взвешенных стратегий
        """
        if isinstance(keys, dict):
            self._keys = list(keys.keys())
        else:
            self._keys = keys

    @abstractmethod
    def get_next_key(
            self,
            current_key_metrics: Optional[Dict[str, KeyMetrics]] = None
    ) -> str:
        """
        Выбирает следующий ключ для использования.

        Args:
            current_key_metrics: Текущие метрики всех ключей (опционально)

        Returns:
            str: Выбранный API ключ

        Raises:
            Exception: Если нет доступных ключей
        """
        raise NotImplementedError

    def update_key_metrics(
            self,
            key: str,
            success: bool,
            response_time: float = 0.0,
            **kwargs
    ):
        """
        Обновляет метрики ключа после запроса (опционально).

        Некоторые стратегии могут хранить собственное состояние
        и обновлять его через этот метод.

        Args:
            key: API ключ
            success: Успешность запроса
            response_time: Время выполнения
            **kwargs: Дополнительные параметры
        """
        pass  # По умолчанию ничего не делаем