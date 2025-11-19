"""
Metrics collector for the rotator
"""

import time
import threading
from collections import defaultdict
from typing import Dict, Any


class EndpointStats:
    """
    Statistics for an endpoint.
    Thread-safe version.
    """

    def __init__(self):
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.avg_response_time = 0.0
        self._lock = threading.RLock()

    def to_dict(self) -> Dict[str, Any]:
        """Serialization to dictionary (thread-safe)"""
        with self._lock:
            return {
                "total_requests": self.total_requests,
                "successful_requests": self.successful_requests,
                "failed_requests": self.failed_requests,
                "avg_response_time": self.avg_response_time,
            }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'EndpointStats':
        """Deserialization from dictionary"""
        stats = EndpointStats()
        for field, value in data.items():
            if hasattr(stats, field) and not field.startswith('_'):
                setattr(stats, field, value)
        return stats

    def update(self, success: bool, response_time: float):
        """
        Updates endpoint statistics (thread-safe).

        Args:
            success: Whether the request was successful
            response_time: Execution time
        """
        with self._lock:
            self.total_requests += 1
            if success:
                self.successful_requests += 1
            else:
                self.failed_requests += 1

            if self.total_requests > 0:
                self.avg_response_time = (
                                                 self.avg_response_time * (self.total_requests - 1) + response_time
                                         ) / self.total_requests


class RotatorMetrics:
    """
    Central metrics collector for the rotator.
    Tracks:
    - General statistics (total requests, successful, errors)
    - Statistics for each endpoint
    - Uptime

    Note: Key metrics are now stored in BaseKeyRotator._key_metrics
    """

    def __init__(self):
        # Statistics by endpoint
        self.endpoint_stats: Dict[str, EndpointStats] = defaultdict(EndpointStats)

        # General statistics
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.start_time = time.time()

        # Thread-safety
        self._lock = threading.RLock()
        self._endpoint_lock = threading.RLock()

    def record_request(
            self,
            key: str,
            endpoint: str,
            success: bool,
            response_time: float,
            is_rate_limited: bool = False
    ):
        """
        Records request metrics.

        Args:
            key: API key (used only for compatibility, key metrics are in the rotator)
            endpoint: URL endpoint
            success: Whether the request was successful
            response_time: Execution time in seconds
            is_rate_limited: Whether rate limit was hit
        """
        # General statistics (thread-safe)
        with self._lock:
            self.total_requests += 1
            if success:
                self.successful_requests += 1
            else:
                self.failed_requests += 1

        # Endpoint statistics (separate lock to minimize contention)
        with self._endpoint_lock:
            self.endpoint_stats[endpoint].update(success, response_time)

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get all metrics as a dictionary (thread-safe).

        Note: Key metrics are now obtained via rotator.get_key_statistics()
        """
        with self._lock, self._endpoint_lock:
            uptime = time.time() - self.start_time
            return {
                "total_requests": self.total_requests,
                "successful_requests": self.successful_requests,
                "failed_requests": self.failed_requests,
                "success_rate": (
                    self.successful_requests / self.total_requests
                    if self.total_requests > 0 else 0.0
                ),
                "uptime_seconds": uptime,
                "endpoint_stats": {
                    k: v.to_dict() for k, v in self.endpoint_stats.items()
                },
            }

    def get_endpoint_stats(self, endpoint: str) -> Dict[str, Any]:
        """Get statistics for a specific endpoint"""
        with self._endpoint_lock:
            if endpoint in self.endpoint_stats:
                return self.endpoint_stats[endpoint].to_dict()
            return {}

    def get_top_endpoints(self, limit: int = 10) -> list:
        """
        Get top endpoints by number of requests.

        Args:
            limit: Number of endpoints

        Returns:
            list: List of tuples (endpoint, total_requests)
        """
        with self._endpoint_lock:
            sorted_endpoints = sorted(
                self.endpoint_stats.items(),
                key=lambda x: x[1].total_requests,
                reverse=True
            )
            return [
                (endpoint, stats.total_requests)
                for endpoint, stats in sorted_endpoints[:limit]
            ]

    def reset(self):
        """Resets all metrics"""
        with self._lock, self._endpoint_lock:
            self.endpoint_stats.clear()
            self.total_requests = 0
            self.successful_requests = 0
            self.failed_requests = 0
            self.start_time = time.time()