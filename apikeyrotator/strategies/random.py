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
        Selects a random key.

        Args:
            current_key_metrics: Not used in this strategy

        Returns:
            str: Randomly selected key
        """
        return random.choice(self._keys)