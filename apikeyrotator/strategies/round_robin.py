"""
Round Robin стратегия ротации
"""

from typing import List, Dict, Optional
from .base import BaseRotationStrategy, KeyMetrics


class RoundRobinRotationStrategy(BaseRotationStrategy):
    """
    Простая последовательная ротация ключей по кругу.

    Переключает ключи по порядку: key1 -> key2 -> key3 -> key1 -> ...

    Это самая простая и предсказуемая стратегия, которая обеспечивает
    равномерное распределение нагрузки между всеми ключами.

    Example:
        >>> strategy = RoundRobinRotationStrategy(['key1', 'key2', 'key3'])
        >>> strategy.get_next_key()  # 'key1'
        >>> strategy.get_next_key()  # 'key2'
        >>> strategy.get_next_key()  # 'key3'
        >>> strategy.get_next_key()  # 'key1'
    """

    def __init__(self, keys: List[str]):
        """
        Инициализирует стратегию Round Robin.

        Args:
            keys: Список API ключей для ротации
        """
        super().__init__(keys)
        self._current_index = 0

    def get_next_key(
            self,
            current_key_metrics: Optional[Dict[str, KeyMetrics]] = None
    ) -> str:
        """
        Выбирает следующий ключ по порядку.

        Args:
            current_key_metrics: Не используется в этой стратегии

        Returns:
            str: Следующий ключ по кругу
        """
        key = self._keys[self._current_index]
        self._current_index = (self._current_index + 1) % len(self._keys)
        return key