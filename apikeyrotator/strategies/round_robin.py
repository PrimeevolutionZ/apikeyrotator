"""
Round Robin rotation strategy
"""

from typing import List, Dict, Optional
import threading
from .base import BaseRotationStrategy, KeyMetrics


class RoundRobinRotationStrategy(BaseRotationStrategy):
    """
    Simple sequential key rotation in a circular manner.

    Switches keys in order: key1 -> key2 -> key3 -> key1 -> ...
    Example:
        >>> strategy = RoundRobinRotationStrategy(['key1', 'key2', 'key3'])
        >>> strategy.get_next_key()  # 'key1'
        >>> strategy.get_next_key()  # 'key2'
        >>> strategy.get_next_key()  # 'key3'
        >>> strategy.get_next_key()  # 'key1'
    """

    def __init__(self, keys: List[str]):
        """
        Initializes Round Robin strategy.

        Args:
            keys: List of API keys for rotation

        Raises:
            ValueError: If the key list is empty
        """
        super().__init__(keys)
        self._current_index = 0
        # Separate lock for index to minimize contention
        self._index_lock = threading.Lock()

    def get_next_key(
            self,
            current_key_metrics: Optional[Dict[str, KeyMetrics]] = None
    ) -> str:
        """
        Selects the next key in order.
        Args:
            current_key_metrics: Not used in this strategy

        Returns:
            str: Next key in the loop

        Raises:
            ValueError: If no keys are available
        """
        with self._lock:
            if not self._keys:
                raise ValueError("No keys available in rotation")

            # Get list of healthy keys
            healthy_keys = self._get_healthy_keys(current_key_metrics)

            if not healthy_keys:
                # Fallback: use all keys if no healthy ones
                healthy_keys = self._keys.copy()

        with self._index_lock:
            # Ensure index is within list bounds
            self._current_index = self._current_index % len(healthy_keys)
            key = healthy_keys[self._current_index]
            self._current_index = (self._current_index + 1) % len(healthy_keys)

        return key

    def __repr__(self):
        with self._lock:
            return f"<RoundRobinStrategy keys={len(self._keys)} current_index={self._current_index}>"