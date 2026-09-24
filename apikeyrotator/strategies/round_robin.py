"""
Round Robin rotation strategy
"""

import time

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

    def __init__(self, keys: list[str]):
        """
        Initializes Round Robin strategy.

        Args:
            keys: List of API keys for rotation

        Raises:
            ValueError: If the key list is empty
        """
        super().__init__(keys)
        self._current_index = 0

    def get_next_key(
            self,
            current_key_metrics: dict[str, KeyMetrics] | None = None
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
            keys = self._keys
            n = len(keys)
            if n == 0:
                raise ValueError("No keys available in rotation")

            start = self._current_index % n
            if current_key_metrics:
                # Walk forward from the current position and take the first
                # available key: O(1) when most keys are healthy, instead of
                # building the full healthy list on every call.
                now = time.time()
                recovery_timeout = self.recovery_timeout
                get = current_key_metrics.get
                available = self._key_available
                for offset in range(n):
                    idx = (start + offset) % n
                    if available(get(keys[idx]), now, recovery_timeout):
                        self._current_index = (idx + 1) % n
                        return keys[idx]

            # No metrics, or no available keys: plain rotation over all keys
            self._current_index = (start + 1) % n
            return keys[start]

    def __repr__(self):
        with self._lock:
            return f"<RoundRobinStrategy keys={len(self._keys)} current_index={self._current_index}>"