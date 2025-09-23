from enum import Enum
from typing import List, Dict, Any, Optional
import time

class RotationStrategy(Enum):
    ROUND_ROBIN = "round_robin"
    WEIGHTED = "weighted"
    LRU = "lru"
    FAILOVER = "failover"
    HEALTH_BASED = "health_based"
    RATE_LIMIT_AWARE = "rate_limit_aware"

class KeyMetrics:
    def __init__(self, key: str):
        self.key = key
        self.success_rate = 1.0
        self.avg_response_time = 0.0
        self.last_used = 0.0
        self.rate_limit_reset = 0.0
        self.requests_remaining = float('inf')
        self.consecutive_failures = 0
        self.is_healthy = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "success_rate": self.success_rate,
            "avg_response_time": self.avg_response_time,
            "last_used": self.last_used,
            "rate_limit_reset": self.rate_limit_reset,
            "requests_remaining": self.requests_remaining,
            "consecutive_failures": self.consecutive_failures,
            "is_healthy": self.is_healthy,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'KeyMetrics':
        metrics = KeyMetrics(data["key"])
        metrics.success_rate = data.get("success_rate", 1.0)
        metrics.avg_response_time = data.get("avg_response_time", 0.0)
        metrics.last_used = data.get("last_used", 0.0)
        metrics.rate_limit_reset = data.get("rate_limit_reset", 0.0)
        metrics.requests_remaining = data.get("requests_remaining", float('inf'))
        metrics.consecutive_failures = data.get("consecutive_failures", 0)
        metrics.is_healthy = data.get("is_healthy", True)
        return metrics

class BaseRotationStrategy:
    def __init__(self, keys: List[str]):
        self._keys = keys

    def get_next_key(self, current_key_metrics: Dict[str, KeyMetrics]) -> str:
        raise NotImplementedError

    def update_key_metrics(self, key: str, success: bool, response_time: float = 0.0, **kwargs):
        pass

class RoundRobinStrategy(BaseRotationStrategy):
    def __init__(self, keys: List[str]):
        super().__init__(keys)
        self._current_index = 0

    def get_next_key(self, current_key_metrics: Dict[str, KeyMetrics]) -> str:
        key = self._keys[self._current_index]
        self._current_index = (self._current_index + 1) % len(self._keys)
        return key

class HealthBasedStrategy(BaseRotationStrategy):
    def __init__(self, keys: List[str], failure_threshold: int = 3, health_check_interval: int = 300):
        super().__init__(keys)
        self.failure_threshold = failure_threshold
        self.health_check_interval = health_check_interval
        self._key_metrics: Dict[str, KeyMetrics] = {key: KeyMetrics(key) for key in keys}

    def get_next_key(self, current_key_metrics: Dict[str, KeyMetrics]) -> str:
        # Update internal metrics with external ones if provided
        for key, metrics in current_key_metrics.items():
            self._key_metrics[key] = metrics

        healthy_keys = [k for k, metrics in self._key_metrics.items() if metrics.is_healthy or (time.time() - metrics.last_used > self.health_check_interval)]

        if not healthy_keys:
            # If no healthy keys, try to re-evaluate all keys (maybe some recovered)
            for key in self._key_metrics:
                self._key_metrics[key].is_healthy = True # Temporarily mark all as healthy to give them a chance
            healthy_keys = list(self._key_metrics.keys())
            if not healthy_keys:
                raise Exception("No keys available for rotation.")

        # Simple round-robin among healthy keys for now
        # In a real implementation, might add more sophisticated selection
        key = random.choice(healthy_keys)
        self._key_metrics[key].last_used = time.time()
        return key

    def update_key_metrics(self, key: str, success: bool, response_time: float = 0.0, **kwargs):
        metrics = self._key_metrics.get(key)
        if not metrics:
            return

        if success:
            metrics.consecutive_failures = 0
            metrics.is_healthy = True
            metrics.success_rate = (metrics.success_rate * 0.9) + (1.0 * 0.1) # Simple moving average
        else:
            metrics.consecutive_failures += 1
            if metrics.consecutive_failures >= self.failure_threshold:
                metrics.is_healthy = False
            metrics.success_rate = (metrics.success_rate * 0.9) + (0.0 * 0.1)
        metrics.avg_response_time = (metrics.avg_response_time * 0.9) + (response_time * 0.1)
        metrics.last_used = time.time()

        # Update rate limit specific metrics if provided
        if 'rate_limit_reset' in kwargs:
            metrics.rate_limit_reset = kwargs['rate_limit_reset']
        if 'requests_remaining' in kwargs:
            metrics.requests_remaining = kwargs['requests_remaining']

# Factory function to create strategy instances
def create_rotation_strategy(strategy_type: RotationStrategy, keys: List[str], **kwargs) -> BaseRotationStrategy:
    if strategy_type == RotationStrategy.ROUND_ROBIN:
        return RoundRobinStrategy(keys)
    elif strategy_type == RotationStrategy.HEALTH_BASED:
        return HealthBasedStrategy(keys, **kwargs)
    # Add other strategies here
    else:
        raise ValueError(f"Unknown rotation strategy: {strategy_type}")


