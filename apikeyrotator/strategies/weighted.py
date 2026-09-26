"""
Weighted rotation strategy
"""

import bisect
import itertools
import random
import time

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

    _PROBES = 4

    def __init__(self, keys: dict[str, float]):
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
        for key, weight in keys.items():
            if not isinstance(weight, (int, float)) or weight < 0:
                raise ValueError(f"Weight for key {key[:4]}**** must be a non-negative number")
        if sum(keys.values()) <= 0:
            raise ValueError("At least one key must have a positive weight")
        self._weights = dict(keys)
        self._keys_list = list(keys.keys())
        self._weights_list = list(keys.values())
        self._rebuild_cumulative()

    def get_next_key(
            self,
            current_key_metrics: dict[str, KeyMetrics] | None = None
    ) -> str:
        """
        Selects key considering weights, filtering out unhealthy keys.

        Args:
            current_key_metrics: Current key metrics for health filtering

        Returns:
            str: Key selected according to weight coefficients
        """
        with self._lock:
            keys_list = self._keys_list
            cum_weights = self._cum_weights
            if not keys_list:
                raise ValueError("No keys available in rotation")
            total = cum_weights[-1] if cum_weights else 0.0

        if total > 0:
            # Fast path: weighted pick via bisect over precomputed cumulative
            # weights (O(log n)); re-draw a few times if the key is unavailable.
            now = time.time()
            recovery_timeout = self.recovery_timeout
            for _ in range(self._PROBES):
                idx = bisect.bisect_right(cum_weights, random.random() * total)
                key = keys_list[min(idx, len(keys_list) - 1)]
                if not current_key_metrics or self._key_available(
                        current_key_metrics.get(key), now, recovery_timeout):
                    return key

        # Slow path: filter to healthy keys and draw among them
        healthy_set = set(self._get_healthy_keys(current_key_metrics))
        with self._lock:
            pairs = list(zip(self._keys_list, self._weights_list))
        filtered = [(k, w) for k, w in pairs if k in healthy_set]
        if not filtered or sum(w for _, w in filtered) <= 0:
            # Fallback: use all keys if no healthy ones
            filtered = pairs
        filtered_keys = [k for k, _ in filtered]
        filtered_weights = [w for _, w in filtered]
        if sum(filtered_weights) <= 0:
            return random.choice(filtered_keys)
        return random.choices(filtered_keys, weights=filtered_weights, k=1)[0]

    def _rebuild_cumulative(self) -> None:
        self._cum_weights = list(itertools.accumulate(self._weights_list))

    def update_keys(self, new_keys: list[str]) -> None:
        """Updates available keys, preserving weights for existing keys."""
        with self._lock:
            self._keys = list(new_keys)
            weights = self._weights
            if weights is None:   # always set by __init__; keeps the type checker informed
                weights = self._weights = {}
            # Filter weights to only keep existing keys
            self._keys_list = [k for k in new_keys if k in weights]
            self._weights_list = [weights[k] for k in self._keys_list]
            # Assign default weight 1.0 for any new keys not in original weights
            for k in new_keys:
                if k not in weights:
                    self._keys_list.append(k)
                    self._weights_list.append(1.0)
                    weights[k] = 1.0
            self._rebuild_cumulative()