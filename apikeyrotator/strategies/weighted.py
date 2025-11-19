"""
Weighted rotation strategy
"""

import random
from typing import Dict, Optional
from .base import BaseRotationStrategy, KeyMetrics


class WeightedRotationStrategy(BaseRotationStrategy):
    """
    Weighted key rotation based on assigned weights.

    Keys with higher weights will be used more frequently.
    Useful when different keys have different limits or priorities.

    Example:
        >>> # 70% requests to key1, 30% to key2
        >>> weights = {'key1': 0.7, 'key2': 0.3}
        >>> strategy = WeightedRotationStrategy(weights)
        >>> strategy.get_next_key()
    """

    def __init__(self, keys: Dict[str, float]):
        """
        Initializes Weighted strategy.

        Args:
            keys: Dict {key: weight}, where weight is selection probability
                  Weights don't have to sum to 1.0

        Example:
            >>> WeightedRotationStrategy({'key1': 2.0, 'key2': 1.0})
            >>> # key1 will be selected twice as often as key2
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
        Selects key considering weights.

        Args:
            current_key_metrics: Not used in this strategy

        Returns:
            str: Key selected according to weight coefficients
        """
        return random.choices(
            self._keys_list,
            weights=self._weights_list,
            k=1
        )[0]