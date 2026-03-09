"""
Weighted rotation strategy
"""

import random
from typing import Dict, List, Optional
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
        Selects key considering weights, filtering out unhealthy keys.

        Args:
            current_key_metrics: Current key metrics for health filtering

        Returns:
            str: Key selected according to weight coefficients
        """
        healthy_keys = self._get_healthy_keys(current_key_metrics)
        healthy_set = set(healthy_keys)

        # Filter weights to only include healthy keys
        filtered_keys = [k for k in self._keys_list if k in healthy_set]
        filtered_weights = [w for k, w in zip(self._keys_list, self._weights_list) if k in healthy_set]

        if not filtered_keys:
            # Fallback: use all keys if no healthy ones
            filtered_keys = self._keys_list
            filtered_weights = self._weights_list

        return random.choices(
            filtered_keys,
            weights=filtered_weights,
            k=1
        )[0]

    def update_keys(self, new_keys: List[str]) -> None:
        """Updates available keys, preserving weights for existing keys."""
        with self._lock:
            self._keys = list(new_keys)
            # Filter weights to only keep existing keys
            self._keys_list = [k for k in new_keys if k in self._weights]
            self._weights_list = [self._weights[k] for k in self._keys_list]
            # Assign default weight 1.0 for any new keys not in original weights
            for k in new_keys:
                if k not in self._weights:
                    self._keys_list.append(k)
                    self._weights_list.append(1.0)
                    self._weights[k] = 1.0