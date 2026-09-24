"""
Health-Based rotation strategy
"""

import time
import random
from typing import List, Dict, Optional
from .base import BaseRotationStrategy, KeyMetrics


class HealthBasedStrategy(BaseRotationStrategy):
    """
    Strategy based on key health.

    Selects only healthy keys (without consecutive failures).
    Unhealthy keys are automatically excluded from rotation and periodically
    rechecked after health_check_interval.

    Attributes:
        failure_threshold: Number of consecutive failures to mark a key as unhealthy
        health_check_interval: Interval in seconds for rechecking unhealthy keys

    Example:
        >>> strategy = HealthBasedStrategy(
        ...     ['key1', 'key2', 'key3'],
        ...     failure_threshold=5,
        ...     health_check_interval=300
        ... )
        >>> strategy.get_next_key()  # Returns only healthy key
    """

    def __init__(
            self,
            keys: List[str],
            failure_threshold: int = 3,
            health_check_interval: int = 300
    ):
        """
        Initializes Health-Based strategy.

        Args:
            keys: List of API keys
            failure_threshold: Number of consecutive failures to mark as unhealthy
            health_check_interval: Time in seconds before rechecking unhealthy keys
        """
        super().__init__(keys)
        self.failure_threshold = failure_threshold
        self.health_check_interval = health_check_interval

        # Create metrics to track health
        self._key_metrics: Dict[str, KeyMetrics] = {
            key: KeyMetrics(key) for key in keys
        }

    def get_next_key(
            self,
            current_key_metrics: Optional[Dict[str, KeyMetrics]] = None
    ) -> str:
        """
        Selects a random healthy key.

        Unhealthy keys are given a probe request once health_check_interval
        seconds have passed since their last failure. If no key is healthy,
        the key whose last failure is the oldest is probed (staggered recovery
        instead of reviving all keys at once - avoids a thundering herd).

        Args:
            current_key_metrics: Current key metrics from rotator

        Returns:
            str: Random healthy key

        Raises:
            ValueError: If no keys are available
        """
        with self._lock:
            keys = self._keys
            if not keys:
                raise ValueError("No keys available for rotation.")

            ext = current_key_metrics or {}
            own = self._key_metrics
            now = time.time()
            threshold = self.failure_threshold
            interval = self.health_check_interval

            healthy_keys = []
            oldest_key, oldest_failure = keys[0], float('inf')
            for k in keys:
                m = ext.get(k) or own.get(k)
                if m is None:
                    # No metrics yet: healthy
                    healthy_keys.append(k)
                    continue
                if m.rate_limit_reset > now:
                    continue
                failures = m.consecutive_failures
                # is_healthy=False without consecutive failures means the key was
                # flagged explicitly (or by a low success rate) - respect that flag.
                if failures < threshold and (m.is_healthy or failures > 0):
                    healthy_keys.append(k)
                elif m.last_failure > 0 and now - m.last_failure >= interval:
                    # Ready for a recheck
                    healthy_keys.append(k)
                elif m.last_failure < oldest_failure:
                    oldest_key, oldest_failure = k, m.last_failure

            if healthy_keys:
                return random.choice(healthy_keys)

            # Staggered recovery: probe the key that failed the longest time ago
            self.logger.info(f"Staggered recovery: probing key {oldest_key[:4]}****")
            return oldest_key

    def update_key_metrics(
            self,
            key: str,
            success: bool,
            response_time: float = 0.0,
            **kwargs
    ):
        """
        Updates key metrics and marks as unhealthy when threshold exceeded.

        Args:
            key: API key
            success: Request success
            response_time: Execution time
            **kwargs: Additional parameters
        """
        with self._lock:
            metrics = self._key_metrics.get(key)
        if not metrics:
            return

        # Update base metrics
        metrics.update_from_request(success, response_time, **kwargs)

        # Additional health logic
        if not success and metrics.consecutive_failures >= self.failure_threshold:
            metrics.is_healthy = False

    def update_keys(self, new_keys: List[str]) -> None:
        """Updates keys, adding metrics for new keys and removing stale ones."""
        with self._lock:
            self._keys = list(new_keys)
            new_set = set(new_keys)
            for key in list(self._key_metrics.keys()):
                if key not in new_set:
                    del self._key_metrics[key]
            for key in new_keys:
                if key not in self._key_metrics:
                    self._key_metrics[key] = KeyMetrics(key)