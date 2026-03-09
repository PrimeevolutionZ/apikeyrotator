"""Data models for metrics"""

import threading
from typing import Dict, Any


class KeyStats:
    """Statistics for a single API key"""

    def __init__(self):
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

    def to_dict(self) -> Dict[str, Any]:
        return {
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
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'KeyStats':
        stats = KeyStats()
        for field, value in data.items():
            if hasattr(stats, field):
                setattr(stats, field, value)
        return stats


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
