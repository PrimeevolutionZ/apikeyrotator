"""
LRU (Least Recently Used) rotation strategy
"""

import time
from typing import List, Dict, Optional
from .base import BaseRotationStrategy, KeyMetrics


class LRURotationStrategy(BaseRotationStrategy):
    """
    Least Recently Used strategy - selects the least recently used key.

    Tracks the last usage time of each key and always
    selects the one that was used the longest ago.

    Useful for even load distribution and preventing
    "forgetting" of rarely used keys.

    Example:
        >>> strategy = LRURotationStrategy(['key1', 'key2', 'key3'])
        >>> strategy.get_next_key()  # Returns key with smallest last_used
    """

    def __init__(self, keys: List[str]):
        """
        Initializes LRU strategy.

        Args:
            keys: List of API keys for rotation
        """
        super().__init__(keys)
        # Create metrics to track usage time
        self._key_metrics: Dict[str, KeyMetrics] = {
            key: KeyMetrics(key) for key in keys
        }

    def get_next_key(
            self,
            current_key_metrics: Optional[Dict[str, KeyMetrics]] = None
    ) -> str:
        """
        Selects the least recently used healthy key.

        Args:
            current_key_metrics: Current key metrics from rotator
                                 If provided, used instead of internal

        Returns:
            str: Least recently used healthy key
        """
        # Use external metrics if provided
        if current_key_metrics:
            for key, metrics in current_key_metrics.items():
                if key in self._key_metrics:
                    self._key_metrics[key] = metrics

        # Filter to healthy keys
        healthy_keys = self._get_healthy_keys(current_key_metrics)
        healthy_set = set(healthy_keys)

        # Find LRU key among healthy keys
        healthy_metrics = {
            k: v for k, v in self._key_metrics.items() if k in healthy_set
        }

        if not healthy_metrics:
            healthy_metrics = self._key_metrics

        lru_key = min(
            healthy_metrics.items(),
            key=lambda x: x[1].last_used
        )

        # Update usage time
        lru_key[1].last_used = time.time()

        return lru_key[0]

    def update_keys(self, new_keys: List[str]) -> None:
        """Updates keys, adding metrics for new keys and removing stale ones."""
        with self._lock:
            self._keys = list(new_keys)
            new_set = set(new_keys)
            # Remove metrics for removed keys
            for key in list(self._key_metrics.keys()):
                if key not in new_set:
                    del self._key_metrics[key]
            # Add metrics for new keys
            for key in new_keys:
                if key not in self._key_metrics:
                    self._key_metrics[key] = KeyMetrics(key)