"""
Base classes for key rotation strategies
"""

import logging
import threading
import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any


class RotationStrategy(Enum):
    """Enumeration of available rotation strategies"""
    ROUND_ROBIN = "round_robin"
    RANDOM = "random"
    WEIGHTED = "weighted"
    LRU = "lru"
    FAILOVER = "failover"
    HEALTH_BASED = "health_based"


# Lock striping: KeyMetrics instances share a small pool of locks instead of owning
# one each - saves memory with thousands of keys; contention is negligible because
# the critical sections are a few attribute updates.
_LOCK_STRIPES = 64
_LOCKS = tuple(threading.Lock() for _ in range(_LOCK_STRIPES))


class KeyMetrics:
    """
    Metrics for a single API key.
    """

    __slots__ = (
        "key", "total_requests", "successful_requests", "failed_requests",
        "avg_response_time", "last_used", "last_success", "last_failure",
        "consecutive_failures", "rate_limit_hits", "is_healthy", "success_rate",
        "rate_limit_reset", "requests_remaining", "_ewma_alpha", "_response_samples", "_lock",
    )

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

        # Parameter for EWMA
        self._ewma_alpha = max(0.01, min(1.0, ewma_alpha))

        # Number of samples used for avg_response_time
        self._response_samples = 0

        # Thread-safety (shared striped lock, non-reentrant)
        self._lock = _LOCKS[hash(key) % _LOCK_STRIPES]

    def to_dict(self) -> dict[str, Any]:
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
    def from_dict(data: dict[str, Any]) -> 'KeyMetrics':
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
        now = time.time()
        with self._lock:
            self.total_requests += 1
            self.last_used = now
            alpha = self._ewma_alpha

            # EWMA: new_value = (1 - alpha) * old_value + alpha * new_observation
            if success:
                self.successful_requests += 1
                self.last_success = now
                self.consecutive_failures = 0
                self.success_rate = (1 - alpha) * self.success_rate + alpha
            else:
                self.failed_requests += 1
                self.last_failure = now
                self.consecutive_failures += 1
                self.success_rate = (1 - alpha) * self.success_rate

            # Update average response time (cumulative average over timed samples only,
            # so requests without timing information don't drag the average down)
            if response_time > 0:
                self._response_samples += 1
                self.avg_response_time += (
                    response_time - self.avg_response_time
                ) / self._response_samples

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
            # An active rate limit is tracked separately (rate_limit_reset) and is
            # checked by is_available(); it must not flip is_healthy, otherwise the
            # key would stay sidelined long after its rate limit window expired.
            if self.consecutive_failures >= 3:
                self.is_healthy = False
            elif self.success_rate < 0.3 and self.total_requests > 10:
                self.is_healthy = False
            else:
                self.is_healthy = True

    def mark_rate_limited(self, until: float) -> None:
        """
        Marks the key as rate limited until the given UNIX timestamp.

        Args:
            until: UNIX timestamp when the rate limit expires
        """
        with self._lock:
            if until > self.rate_limit_reset:
                self.rate_limit_reset = until
            self.requests_remaining = 0

    def is_available(self, now: float | None = None, recovery_timeout: float | None = None) -> bool:
        """
        Whether the key can be used right now.

        A key is available if it is not rate limited and is healthy. An unhealthy
        key becomes available again for a probe request once ``recovery_timeout``
        seconds have passed since its last failure (half-open behaviour), so that
        a transient outage doesn't exclude a key from rotation forever.

        Args:
            now: Current time (defaults to time.time())
            recovery_timeout: Seconds after the last failure when an unhealthy key
                              may be retried. None disables automatic recovery.
        """
        # Hot path (called for every key on every selection): plain attribute reads
        # are atomic in CPython, so no lock is needed for this read-only check.
        if now is None:
            now = time.time()
        if self.rate_limit_reset > now:
            return False
        if self.is_healthy:
            return True
        return (
            recovery_timeout is not None
            and self.last_failure > 0
            and now - self.last_failure >= recovery_timeout
        )

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

    Attributes:
        recovery_timeout: Seconds after the last failure when an unhealthy key is
                          given another chance (probe). Set to None to disable.
    """

    recovery_timeout: float | None = 60.0

    def __init__(self, keys: list[str] | dict[str, float]):
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

        self.logger = logging.getLogger(__name__)

    @abstractmethod
    def get_next_key(
            self,
            current_key_metrics: dict[str, KeyMetrics] | None = None
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

    def use_external_metrics(self) -> None:
        """
        Called by the rotator: it owns per-key metrics and passes them to every
        get_next_key() call, so strategies can free internal per-key copies.
        """

    def update_keys(self, new_keys: list[str]) -> None:
        """
        Updates the list of available keys (e.g., after key removal).

        Args:
            new_keys: Updated list of API keys
        """
        with self._lock:
            self._keys = list(new_keys)

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
        current_key_metrics: dict[str, KeyMetrics] | None = None
    ) -> list[str]:
        """
        Returns list of healthy keys.

        Args:
            current_key_metrics: Key metrics

        Returns:
            List[str]: List of healthy keys
        """
        with self._lock:
            keys = self._keys.copy()

        if current_key_metrics is None:
            return keys

        now = time.time()
        recovery_timeout = self.recovery_timeout
        get = current_key_metrics.get
        available = self._key_available
        healthy = [key for key in keys if available(get(key), now, recovery_timeout)]

        # If no healthy keys, return all
        return healthy if healthy else keys

    @staticmethod
    def _key_available(metrics: KeyMetrics | None, now: float, recovery_timeout: float | None) -> bool:
        """Availability check that treats keys without metrics as available."""
        return metrics is None or metrics.is_available(now, recovery_timeout)
