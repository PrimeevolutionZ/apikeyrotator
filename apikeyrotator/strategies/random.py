"""
Random rotation strategy
"""

import random
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
        healthy_keys = self._get_healthy_keys(current_key_metrics)
        return random.choice(healthy_keys)