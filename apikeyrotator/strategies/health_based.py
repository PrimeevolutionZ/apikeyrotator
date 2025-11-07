"""
Health-Based стратегия ротации
"""

import time
import random
from typing import List, Dict, Optional
from .base import BaseRotationStrategy, KeyMetrics


class HealthBasedStrategy(BaseRotationStrategy):
    """
    Стратегия на основе здоровья ключей.

    Выбирает только здоровые ключи (без последовательных ошибок).
    Нездоровые ключи автоматически исключаются из ротации и периодически
    проверяются повторно после health_check_interval.

    Attributes:
        failure_threshold: Количество последовательных ошибок для пометки ключа как нездорового
        health_check_interval: Интервал в секундах для повторной проверки нездоровых ключей

    Example:
        >>> strategy = HealthBasedStrategy(
        ...     ['key1', 'key2', 'key3'],
        ...     failure_threshold=5,
        ...     health_check_interval=300
        ... )
        >>> strategy.get_next_key()  # Вернет только здоровый ключ
    """

    def __init__(
            self,
            keys: List[str],
            failure_threshold: int = 3,
            health_check_interval: int = 300
    ):
        """
        Инициализирует стратегию Health-Based.

        Args:
            keys: Список API ключей
            failure_threshold: Количество последовательных ошибок для пометки как нездоровый
            health_check_interval: Время в секундах до повторной проверки нездоровых ключей
        """
        super().__init__(keys)
        self.failure_threshold = failure_threshold
        self.health_check_interval = health_check_interval

        # Создаем метрики для отслеживания здоровья
        self._key_metrics: Dict[str, KeyMetrics] = {
            key: KeyMetrics(key) for key in keys
        }

    def get_next_key(
            self,
            current_key_metrics: Optional[Dict[str, KeyMetrics]] = None
    ) -> str:
        """
        Выбирает случайный здоровый ключ.

        Args:
            current_key_metrics: Текущие метрики ключей из ротатора

        Returns:
            str: Случайный здоровый ключ

        Raises:
            Exception: Если нет доступных здоровых ключей
        """
        # Используем внешние метрики если они предоставлены
        if current_key_metrics:
            for key, metrics in current_key_metrics.items():
                if key in self._key_metrics:
                    self._key_metrics[key] = metrics

        # Находим здоровые ключи или те, что готовы к повторной проверке
        current_time = time.time()
        healthy_keys = [
            k for k, metrics in self._key_metrics.items()
            if metrics.is_healthy or (
                    current_time - metrics.last_used > self.health_check_interval
            )
        ]

        # Если нет здоровых ключей, сбрасываем все как здоровые
        if not healthy_keys:
            for key in self._key_metrics:
                self._key_metrics[key].is_healthy = True
            healthy_keys = list(self._key_metrics.keys())

        if not healthy_keys:
            raise Exception("No keys available for rotation.")

        # Выбираем случайный здоровый ключ
        key = random.choice(healthy_keys)
        self._key_metrics[key].last_used = time.time()
        return key

    def update_key_metrics(
            self,
            key: str,
            success: bool,
            response_time: float = 0.0,
            **kwargs
    ):
        """
        Обновляет метрики ключа и помечает как нездоровый при превышении порога.

        Args:
            key: API ключ
            success: Успешность запроса
            response_time: Время выполнения
            **kwargs: Дополнительные параметры
        """
        metrics = self._key_metrics.get(key)
        if not metrics:
            return

        # Обновляем базовые метрики
        metrics.update_from_request(success, response_time, **kwargs)

        # Дополнительная логика здоровья
        if not success and metrics.consecutive_failures >= self.failure_threshold:
            metrics.is_healthy = False