"""
Weighted (взвешенная) стратегия ротации
"""

import random
from typing import Dict, Optional
from .base import BaseRotationStrategy, KeyMetrics


class WeightedRotationStrategy(BaseRotationStrategy):
    """
    Взвешенная ротация ключей на основе заданных весов.

    Ключи с большим весом будут использоваться чаще.
    Полезно когда разные ключи имеют разные лимиты или приоритеты.

    Example:
        >>> # 70% запросов на key1, 30% на key2
        >>> weights = {'key1': 0.7, 'key2': 0.3}
        >>> strategy = WeightedRotationStrategy(weights)
        >>> strategy.get_next_key()
    """

    def __init__(self, keys: Dict[str, float]):
        """
        Инициализирует стратегию Weighted.

        Args:
            keys: Словарь {ключ: вес}, где вес - это вероятность выбора
                  Веса не обязательно должны суммироваться в 1.0

        Example:
            >>> WeightedRotationStrategy({'key1': 2.0, 'key2': 1.0})
            >>> # key1 будет выбираться в 2 раза чаще чем key2
        """
        super().__init__(keys)
        self._weights = keys
        self._keys_list = list(keys.keys())
        self._weights_list = list(keys.values())

    def get_next_key(
            self,
            current_key_metrics: Optional[Dict[str, KeyMetrics]] = None
    ) -> str:
        """
        Выбирает ключ с учетом весов.

        Args:
            current_key_metrics: Не используется в этой стратегии

        Returns:
            str: Ключ, выбранный с учетом весовых коэффициентов
        """
        return random.choices(
            self._keys_list,
            weights=self._weights_list,
            k=1
        )[0]