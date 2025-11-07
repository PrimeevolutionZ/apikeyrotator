"""
Random стратегия ротации
"""

import random
from typing import List, Dict, Optional
from .base import BaseRotationStrategy, KeyMetrics


class RandomRotationStrategy(BaseRotationStrategy):
    """
    Случайный выбор ключа из доступных.

    На каждом запросе выбирается случайный ключ из списка.
    Полезно для избежания предсказуемых паттернов использования.

    Example:
        >>> strategy = RandomRotationStrategy(['key1', 'key2', 'key3'])
        >>> strategy.get_next_key()  # Случайный ключ из списка
    """

    def __init__(self, keys: List[str]):
        """
        Инициализирует стратегию Random.

        Args:
            keys: Список API ключей для ротации
        """
        super().__init__(keys)

    def get_next_key(
            self,
            current_key_metrics: Optional[Dict[str, KeyMetrics]] = None
    ) -> str:
        """
        Выбирает случайный ключ.

        Args:
            current_key_metrics: Не используется в этой стратегии

        Returns:
            str: Случайно выбранный ключ
        """
        return random.choice(self._keys)