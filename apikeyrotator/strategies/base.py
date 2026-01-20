"""
Base classes for key rotation strategies
"""

from enum import Enum
from typing import List, Dict, Any, Optional, Union
from abc import ABC, abstractmethod
import time
import threading
import logging

class RotationStrategy(Enum):
    """Enumeration of available rotation strategies"""
    ROUND_ROBIN = "round_robin"
    RANDOM = "random"
    WEIGHTED = "weighted"
    LRU = "lru"
    FAILOVER = "failover"
    HEALTH_BASED = "health_based"
    RATE_LIMIT_AWARE = "rate_limit_aware"


class KeyMetrics:
    """
    Metrics for a single API key.
    """

    def __init__(self, key: str, ewma_alpha: float = 0.1):
        """
        Args:
            key: API key
            ewma_alpha: Coefficient for EWMA (0 < alpha <= 1).
                       Lower = smoother average
        """
        self.key = key
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.avg_response_time = 0.0
        self.last_used = 0.0
        self.last_success = 0.0
        self.last_failure = 0.0
        self.consecutive_failures = 0
        self.rate_limit_hits = 0
        self.is_healthy = True

        # Additional fields
        self.success_rate = 1.0
        self.rate_limit_reset = 0.0
        self.requests_remaining = float('inf')

        # NEW: Parameter for EWMA
        self._ewma_alpha = max(0.01, min(1.0, ewma_alpha))

        # Thread-safety
        self._lock = threading.RLock()

    def to_dict(self) -> Dict[str, Any]:
        """Serialization of metrics to dictionary (thread-safe)"""
        with self._lock:
            return {
                "key": self.key,
                "total_requests": self.total_requests,
                "successful_requests": self.successful_requests,
                "failed_requests": self.failed_requests,
                "avg_response_time": self.avg_response_time,
                "last_used": self.last_used,
                "last_success": self.last_success,
                "last_failure": self.last_failure,
                "consecutive_failures": self.consecutive_failures,
                "rate_limit_hits": self.rate_limit_hits,
                "is_healthy": self.is_healthy,
                "success_rate": self.success_rate,
                "rate_limit_reset": self.rate_limit_reset,
                "requests_remaining": self.requests_remaining,
            }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'KeyMetrics':
        """Deserialization of metrics from dictionary"""
        metrics = KeyMetrics(data["key"])
        for field, value in data.items():
            if hasattr(metrics, field) and not field.startswith('_'):
                setattr(metrics, field, value)
        return metrics

    def update_from_request(
        self,
        success: bool,
        response_time: float = 0.0,
        is_rate_limited: bool = False,
        **kwargs
    ):
        """
        Updates metrics based on request result.

        Args:
            success: Whether the request was successful
            response_time: Request execution time in seconds
            is_rate_limited: Whether rate limit was hit
            **kwargs: Additional parameters (rate_limit_reset, requests_remaining)
        """
        with self._lock:
            self.total_requests += 1
            self.last_used = time.time()

            if success:
                self.successful_requests += 1
                self.last_success = time.time()
                self.consecutive_failures = 0

                # new_value = (1 - alpha) * old_value + alpha * new_observation
                self.success_rate = (1 - self._ewma_alpha) * self.success_rate + self._ewma_alpha * 1.0
            else:
                self.failed_requests += 1
                self.last_failure = time.time()
                self.consecutive_failures += 1

                # FIXED: Correct EWMA formula for failure
                self.success_rate = (1 - self._ewma_alpha) * self.success_rate + self._ewma_alpha * 0.0

            # Update average response time (simple moving average)
            if self.total_requests > 0 and response_time > 0:
                self.avg_response_time = (
                    self.avg_response_time * (self.total_requests - 1) + response_time
                ) / self.total_requests

            # Rate-limit information
            if is_rate_limited:
                self.rate_limit_hits += 1

            if 'rate_limit_reset' in kwargs:
                self.rate_limit_reset = kwargs['rate_limit_reset']

            if 'requests_remaining' in kwargs:
                self.requests_remaining = kwargs['requests_remaining']

            # Automatic key health determination
            # Key is considered unhealthy if:
            # - 3+ consecutive failures
            # - Success rate < 0.3
            # - Rate limit active and not yet expired
            if self.consecutive_failures >= 3:
                self.is_healthy = False
            elif self.success_rate < 0.3 and self.total_requests > 10:
                self.is_healthy = False
            elif self.rate_limit_reset > time.time():
                self.is_healthy = False
            else:
                self.is_healthy = True

    def get_score(self) -> float:
        """
        Computes key score for weighted/health-based strategies.

        Returns:
            float: Score from 0 to 1, where 1 = best key
        """
        with self._lock:
            if not self.is_healthy:
                return 0.0

            # Check rate limit
            if self.rate_limit_reset > time.time():
                return 0.0

            # Combine factors:
            # - Success rate (weight 0.5)
            # - Inverse response time (weight 0.3)
            # - Recency of use (weight 0.2)

            success_score = self.success_rate * 0.5

            # Normalize response time (faster = better)
            if self.avg_response_time > 0:
                # Assume 10 seconds is very slow
                time_score = max(0, 1 - (self.avg_response_time / 10.0)) * 0.3
            else:
                time_score = 0.3

            # Prefer keys not used recently (load balancing)
            if self.last_used > 0:
                time_since_use = time.time() - self.last_used
                # Normalize: 60 seconds = maximum advantage
                recency_score = min(1.0, time_since_use / 60.0) * 0.2
            else:
                recency_score = 0.2

            return success_score + time_score + recency_score


class BaseRotationStrategy(ABC):
    """
    Base abstract class for all rotation strategies.
    """

    def __init__(self, keys: Union[List[str], Dict[str, float]]):
        """
        Args:
            keys: List of keys or dict {key: weight} for weighted strategies

        Raises:
            ValueError: If keys is empty or invalid
        """
        if isinstance(keys, dict):
            if not keys:
                raise ValueError("Keys dictionary cannot be empty")
            self._keys = list(keys.keys())
            self._weights = keys
        else:
            if not keys:
                raise ValueError("Keys list cannot be empty")
            self._keys = list(keys)  # Copy for safety
            self._weights = None

        # Thread-safety for strategies
        self._lock = threading.RLock()

        # Исправлено: инициализация логгера
        self.logger = logging.getLogger(__name__)

    @abstractmethod
    def get_next_key(
            self,
            current_key_metrics: Optional[Dict[str, KeyMetrics]] = None
    ) -> str:
        """
        Selects the next key to use.

        Args:
            current_key_metrics: Current metrics for all keys (optional)

        Returns:
            str: Selected API key

        Raises:
            ValueError: If no keys are available
        """
        raise NotImplementedError

    def update_key_metrics(
            self,
            key: str,
            success: bool,
            response_time: float = 0.0,
            **kwargs
    ):
        """
        Updates key metrics after request (optional).

        Some strategies may store their own state
        and update it via this method.

        Args:
            key: API key
            success: Whether the request was successful
            response_time: Execution time
            **kwargs: Additional parameters
        """
        pass  # By default do nothing

    def _get_healthy_keys(
        self,
        current_key_metrics: Optional[Dict[str, KeyMetrics]] = None
    ) -> List[str]:
        """
        Returns list of healthy keys.

        Args:
            current_key_metrics: Key metrics

        Returns:
            List[str]: List of healthy keys
        """
        with self._lock:
            if current_key_metrics is None:
                return self._keys.copy()

            healthy = []
            for key in self._keys:
                if key in current_key_metrics:
                    metrics = current_key_metrics[key]
                    # Key is healthy if:
                    # - is_healthy = True
                    # - rate limit expired
                    if metrics.is_healthy and metrics.rate_limit_reset <= time.time():
                        healthy.append(key)
                else:
                    # If no metrics, consider key healthy
                    healthy.append(key)

            # If no healthy keys, return all
            return healthy if healthy else self._keys.copy()