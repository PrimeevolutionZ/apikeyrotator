from enum import Enum
from typing import List, Dict, Any, Optional, Union
import time
import random


class RotationStrategy(Enum):
    ROUND_ROBIN = "round_robin"
    RANDOM = "random"
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
    def __init__(self, keys: Union[List[str], Dict[str, float]]):
        if isinstance(keys, dict):
            self._keys = list(keys.keys())
        else:
            self._keys = keys

    def get_next_key(self, current_key_metrics: Optional[Dict[str, KeyMetrics]] = None) -> str:
        raise NotImplementedError

    def update_key_metrics(self, key: str, success: bool, response_time: float = 0.0, **kwargs):
        pass


class RoundRobinRotationStrategy(BaseRotationStrategy):
    """Простая последовательная ротация ключей"""

    def __init__(self, keys: List[str]):
        super().__init__(keys)
        self._current_index = 0

    def get_next_key(self, current_key_metrics: Optional[Dict[str, KeyMetrics]] = None) -> str:
        key = self._keys[self._current_index]
        self._current_index = (self._current_index + 1) % len(self._keys)
        return key


class RandomRotationStrategy(BaseRotationStrategy):
    """Случайный выбор ключа"""

    def __init__(self, keys: List[str]):
        super().__init__(keys)

    def get_next_key(self, current_key_metrics: Optional[Dict[str, KeyMetrics]] = None) -> str:
        return random.choice(self._keys)


class WeightedRotationStrategy(BaseRotationStrategy):
    """Взвешенная ротация ключей"""

    def __init__(self, keys: Dict[str, float]):
        super().__init__(keys)
        self._weights = keys
        self._keys_list = list(keys.keys())
        self._weights_list = list(keys.values())

    def get_next_key(self, current_key_metrics: Optional[Dict[str, KeyMetrics]] = None) -> str:
        return random.choices(self._keys_list, weights=self._weights_list, k=1)[0]


class LRURotationStrategy(BaseRotationStrategy):
    """Least Recently Used - выбирает наименее недавно использованный ключ"""

    def __init__(self, keys: List[str]):
        super().__init__(keys)
        self._key_metrics: Dict[str, KeyMetrics] = {key: KeyMetrics(key) for key in keys}

    def get_next_key(self, current_key_metrics: Optional[Dict[str, KeyMetrics]] = None) -> str:
        if current_key_metrics:
            for key, metrics in current_key_metrics.items():
                self._key_metrics[key] = metrics

        # Находим ключ с наименьшим last_used
        lru_key = min(self._key_metrics.items(), key=lambda x: x[1].last_used)
        lru_key[1].last_used = time.time()
        return lru_key[0]


class HealthBasedStrategy(BaseRotationStrategy):
    """Выбирает только здоровые ключи"""

    def __init__(self, keys: List[str], failure_threshold: int = 3, health_check_interval: int = 300):
        super().__init__(keys)
        self.failure_threshold = failure_threshold
        self.health_check_interval = health_check_interval
        self._key_metrics: Dict[str, KeyMetrics] = {key: KeyMetrics(key) for key in keys}

    def get_next_key(self, current_key_metrics: Optional[Dict[str, KeyMetrics]] = None) -> str:
        if current_key_metrics:
            for key, metrics in current_key_metrics.items():
                self._key_metrics[key] = metrics

        healthy_keys = [
            k for k, metrics in self._key_metrics.items()
            if metrics.is_healthy or (time.time() - metrics.last_used > self.health_check_interval)
        ]

        if not healthy_keys:
            # Сбрасываем все ключи как здоровые для повторной попытки
            for key in self._key_metrics:
                self._key_metrics[key].is_healthy = True
            healthy_keys = list(self._key_metrics.keys())
            if not healthy_keys:
                raise Exception("No keys available for rotation.")

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
            metrics.success_rate = (metrics.success_rate * 0.9) + (1.0 * 0.1)
        else:
            metrics.consecutive_failures += 1
            if metrics.consecutive_failures >= self.failure_threshold:
                metrics.is_healthy = False
            metrics.success_rate = (metrics.success_rate * 0.9) + (0.0 * 0.1)

        metrics.avg_response_time = (metrics.avg_response_time * 0.9) + (response_time * 0.1)
        metrics.last_used = time.time()

        if 'rate_limit_reset' in kwargs:
            metrics.rate_limit_reset = kwargs['rate_limit_reset']
        if 'requests_remaining' in kwargs:
            metrics.requests_remaining = kwargs['requests_remaining']


# Старые имена для обратной совместимости
RoundRobinStrategy = RoundRobinRotationStrategy


def create_rotation_strategy(
        strategy_type: Union[str, RotationStrategy],
        keys: Union[List[str], Dict[str, float]],
        **kwargs
) -> BaseRotationStrategy:
    """
    Фабричная функция для создания стратегии ротации

    Args:
        strategy_type: Тип стратегии ('round_robin', 'random', 'weighted', etc.)
        keys: Список ключей или словарь с весами для weighted стратегии
        **kwargs: Дополнительные параметры для конкретной стратегии

    Returns:
        BaseRotationStrategy: Экземпляр стратегии ротации
    """
    if isinstance(strategy_type, str):
        strategy_type = strategy_type.lower()
    else:
        strategy_type = strategy_type.value

    if strategy_type == "round_robin" or strategy_type == RotationStrategy.ROUND_ROBIN.value:
        return RoundRobinRotationStrategy(keys)
    elif strategy_type == "random" or strategy_type == RotationStrategy.RANDOM.value:
        return RandomRotationStrategy(keys)
    elif strategy_type == "weighted" or strategy_type == RotationStrategy.WEIGHTED.value:
        if not isinstance(keys, dict):
            raise ValueError("Weighted strategy requires a dictionary of keys with weights")
        return WeightedRotationStrategy(keys)
    elif strategy_type == "lru" or strategy_type == RotationStrategy.LRU.value:
        return LRURotationStrategy(keys)
    elif strategy_type == "health_based" or strategy_type == RotationStrategy.HEALTH_BASED.value:
        return HealthBasedStrategy(keys, **kwargs)
    else:
        raise ValueError(f"Unknown rotation strategy: {strategy_type}")