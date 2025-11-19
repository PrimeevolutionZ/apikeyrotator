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

        Args:
            current_key_metrics: Current key metrics from rotator

        Returns:
            str: Random healthy key

        Raises:
            Exception: If no healthy keys available
        """
        # Use external metrics if provided
        if current_key_metrics:
            for key, metrics in current_key_metrics.items():
                if key in self._key_metrics:
                    self._key_metrics[key] = metrics

        # Find healthy keys or those ready for recheck
        current_time = time.time()
        healthy_keys = [
            k for k, metrics in self._key_metrics.items()
            if metrics.is_healthy or (
                    current_time - metrics.last_used > self.health_check_interval
            )
        ]

        # If no healthy keys, reset all as healthy
        if not healthy_keys:
            for key in self._key_metrics:
                self._key_metrics[key].is_healthy = True
            healthy_keys = list(self._key_metrics.keys())

        if not healthy_keys:
            raise Exception("No keys available for rotation.")

        # Select random healthy key
        key = random.choice(healthy_keys)
        self._key_metrics[key].last_used = time.time()
        return key

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
        metrics = self._key_metrics.get(key)
        if not metrics:
            return

        # Update base metrics
        metrics.update_from_request(success, response_time, **kwargs)

        # Additional health logic
        if not success and metrics.consecutive_failures >= self.failure_threshold:
            metrics.is_healthy = False