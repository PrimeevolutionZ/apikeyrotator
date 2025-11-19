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
        Selects the key with the smallest last usage time.

        Args:
            current_key_metrics: Current key metrics from rotator
                                 If provided, used instead of internal

        Returns:
            str: Least recently used key
        """
        # Use external metrics if provided
        if current_key_metrics:
            for key, metrics in current_key_metrics.items():
                if key in self._key_metrics:
                    self._key_metrics[key] = metrics

        # Find key with smallest last_used
        lru_key = min(
            self._key_metrics.items(),
            key=lambda x: x[1].last_used
        )

        # Update usage time
        lru_key[1].last_used = time.time()

        return lru_key[0]