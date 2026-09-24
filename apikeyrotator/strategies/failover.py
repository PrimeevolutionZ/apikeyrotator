"""
Failover rotation strategy
"""

import time

from .base import BaseRotationStrategy, KeyMetrics


class FailoverRotationStrategy(BaseRotationStrategy):
    """
    Priority order: always use the first available key; the next keys are
    backups used only while the earlier ones are rate limited or unhealthy.

    Useful for a primary key (e.g. a paid plan) plus fallback keys. A key that
    recovers (rate limit expired / recovery_timeout passed) takes over again.

    Example:
        >>> strategy = FailoverRotationStrategy(['primary', 'backup1', 'backup2'])
        >>> strategy.get_next_key()  # 'primary' until it is limited or failing
    """

    def __init__(self, keys: list[str]):
        super().__init__(keys)

    def get_next_key(
            self,
            current_key_metrics: dict[str, KeyMetrics] | None = None
    ) -> str:
        """
        Returns the first available key in priority order.

        Args:
            current_key_metrics: Current key metrics for health filtering

        Returns:
            str: Highest-priority available key (the first key if none is available)
        """
        with self._lock:
            keys = self._keys
            if not keys:
                raise ValueError("No keys available in rotation")
            if current_key_metrics:
                now = time.time()
                recovery_timeout = self.recovery_timeout
                get = current_key_metrics.get
                available = self._key_available
                for key in keys:
                    if available(get(key), now, recovery_timeout):
                        return key
            return keys[0]
