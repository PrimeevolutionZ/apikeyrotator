"""
Random rotation strategy
"""

import random
import time
from typing import List, Dict, Optional
from .base import BaseRotationStrategy, KeyMetrics


class RandomRotationStrategy(BaseRotationStrategy):
    """
    Random key selection from available keys.

    On each request, a random key is selected from the list.
    Useful for avoiding predictable usage patterns.

    Example:
        >>> strategy = RandomRotationStrategy(['key1', 'key2', 'key3'])
        >>> strategy.get_next_key()  # Random key from list
    """

    _PROBES = 4

    def __init__(self, keys: List[str]):
        """
        Initializes Random strategy.

        Args:
            keys: List of API keys for rotation
        """
        super().__init__(keys)

    def get_next_key(
            self,
            current_key_metrics: Optional[Dict[str, KeyMetrics]] = None
    ) -> str:
        """
        Selects a random key from healthy keys.

        Args:
            current_key_metrics: Current key metrics for health filtering

        Returns:
            str: Randomly selected healthy key
        """
        with self._lock:
            keys = self._keys
            if not keys:
                raise ValueError("No keys available in rotation")
            if not current_key_metrics:
                return random.choice(keys)
            # Fast path: a few random probes find an available key in O(1)
            # when most keys are healthy; fall back to a full scan otherwise.
            now = time.time()
            recovery_timeout = self.recovery_timeout
            for _ in range(self._PROBES):
                key = random.choice(keys)
                if self._key_available(current_key_metrics.get(key), now, recovery_timeout):
                    return key
        return random.choice(self._get_healthy_keys(current_key_metrics))