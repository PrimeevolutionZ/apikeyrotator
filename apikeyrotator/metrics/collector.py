# ===========================================
# metrics/models.py
# ===========================================
"""Модели данных для метрик"""

from typing import Dict, Any


class KeyStats:
    """Статистика для одного API ключа"""

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
    """Статистика для endpoint"""

    def __init__(self):
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.avg_response_time = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "avg_response_time": self.avg_response_time,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'EndpointStats':
        stats = EndpointStats()
        for field, value in data.items():
            if hasattr(stats, field):
                setattr(stats, field, value)
        return stats


# ===========================================
# metrics/collector.py
# ===========================================
"""Сборщик метрик"""

import time
from collections import defaultdict
from typing import Dict, Any
from .models import KeyStats, EndpointStats


class RotatorMetrics:
    """
    Центральный сборщик метрик для ротатора.

    Отслеживает:
    - Общую статистику (всего запросов, успешных, ошибок)
    - Статистику по каждому ключу
    - Статистику по каждому endpoint
    - Время работы (uptime)
    """

    def __init__(self):
        self.key_stats: Dict[str, KeyStats] = defaultdict(KeyStats)
        self.endpoint_stats: Dict[str, EndpointStats] = defaultdict(EndpointStats)
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.start_time = time.time()

    def record_request(
            self,
            key: str,
            endpoint: str,
            success: bool,
            response_time: float,
            is_rate_limited: bool = False
    ):
        """
        Записывает метрики запроса.

        Args:
            key: API ключ
            endpoint: URL endpoint
            success: Успешность запроса
            response_time: Время выполнения в секундах
            is_rate_limited: Был ли rate limit
        """
        # Общая статистика
        self.total_requests += 1
        if success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1

        # Статистика ключа
        key_stat = self.key_stats[key]
        key_stat.total_requests += 1
        key_stat.last_used = time.time()

        if success:
            key_stat.successful_requests += 1
            key_stat.last_success = time.time()
            key_stat.consecutive_failures = 0
        else:
            key_stat.failed_requests += 1
            key_stat.last_failure = time.time()
            key_stat.consecutive_failures += 1

        if is_rate_limited:
            key_stat.rate_limit_hits += 1

        # Обновляем среднее время ответа
        if key_stat.total_requests > 0:
            key_stat.avg_response_time = (
                                                 key_stat.avg_response_time * (
                                                     key_stat.total_requests - 1) + response_time
                                         ) / key_stat.total_requests

        # Статистика endpoint
        ep_stat = self.endpoint_stats[endpoint]
        ep_stat.total_requests += 1
        if success:
            ep_stat.successful_requests += 1
        else:
            ep_stat.failed_requests += 1

        if ep_stat.total_requests > 0:
            ep_stat.avg_response_time = (
                                                ep_stat.avg_response_time * (ep_stat.total_requests - 1) + response_time
                                        ) / ep_stat.total_requests

    def get_metrics(self) -> Dict[str, Any]:
        """Получить все метрики в виде словаря"""
        uptime = time.time() - self.start_time
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "uptime_seconds": uptime,
            "key_stats": {k: v.to_dict() for k, v in self.key_stats.items()},
            "endpoint_stats": {k: v.to_dict() for k, v in self.endpoint_stats.items()},
        }