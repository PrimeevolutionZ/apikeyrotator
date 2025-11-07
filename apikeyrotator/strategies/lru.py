"""
LRU (Least Recently Used) стратегия ротации
"""

import time
from typing import List, Dict, Optional
from .base import BaseRotationStrategy, KeyMetrics


class LRURotationStrategy(BaseRotationStrategy):
    """
    Стратегия Least Recently Used - выбирает наименее недавно использованный ключ.

    Отслеживает время последнего использования каждого ключа и всегда
    выбирает тот, который использовался давнее всего.

    Полезно для равномерного распределения нагрузки и предотвращения
    "забывания" редко используемых ключей.

    Example:
        >>> strategy = LRURotationStrategy(['key1', 'key2', 'key3'])
        >>> strategy.get_next_key()  # Вернет ключ с наименьшим last_used
    """

    def __init__(self, keys: List[str]):
        """
        Инициализирует стратегию LRU.

        Args:
            keys: Список API ключей для ротации
        """
        super().__init__(keys)
        # Создаем метрики для отслеживания времени использования
        self._key_metrics: Dict[str, KeyMetrics] = {
            key: KeyMetrics(key) for key in keys
        }

    def get_next_key(
            self,
            current_key_metrics: Optional[Dict[str, KeyMetrics]] = None
    ) -> str:
        """
        Выбирает ключ с наименьшим временем последнего использования.

        Args:
            current_key_metrics: Текущие метрики ключей из ротатора
                                 Если предоставлены, используются вместо внутренних

        Returns:
            str: Наименее недавно использованный ключ
        """
        # Используем внешние метрики если они предоставлены
        if current_key_metrics:
            for key, metrics in current_key_metrics.items():
                if key in self._key_metrics:
                    self._key_metrics[key] = metrics

        # Находим ключ с наименьшим last_used
        lru_key = min(
            self._key_metrics.items(),
            key=lambda x: x[1].last_used
        )

        # Обновляем время использования
        lru_key[1].last_used = time.time()

        return lru_key[0]