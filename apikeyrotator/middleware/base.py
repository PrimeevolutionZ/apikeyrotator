from abc import ABC, abstractmethod
from typing import Dict, List, Protocol, Optional, Any
from dataclasses import dataclass, field
import logging
import asyncio


@dataclass
class KeyMetrics:
    """Метрики для отдельного ключа"""
    key: str
    request_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    rate_limit_count: int = 0
    avg_response_time: float = 0.0
    is_healthy: bool = True
    consecutive_failures: int = 0
    last_used_at: Optional[float] = None
    created_at: float = field(default_factory=lambda: __import__('time').time())

    def update_from_request(
            self,
            success: bool,
            response_time: float,
            is_rate_limited: bool = False
    ) -> None:
        import time
        self.request_count += 1
        self.last_used_at = time.time()

        if success:
            self.success_count += 1
            self.consecutive_failures = 0
            self.avg_response_time = (
                    (self.avg_response_time * (self.success_count - 1) + response_time)
                    / self.success_count
            )
        else:
            self.failure_count += 1
            self.consecutive_failures += 1

        if is_rate_limited:
            self.rate_limit_count += 1

        if self.consecutive_failures >= 3:
            self.is_healthy = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            'key': self.key[:4] + '****',
            'request_count': self.request_count,
            'success_count': self.success_count,
            'failure_count': self.failure_count,
            'rate_limit_count': self.rate_limit_count,
            'avg_response_time': round(self.avg_response_time, 3),
            'is_healthy': self.is_healthy,
            'consecutive_failures': self.consecutive_failures,
        }


class RotatorMiddleware(ABC):
    """
    Абстрактный базовый класс для middleware.
    Поддерживает и синхронные, и асинхронные методы.
    """

    # --- Async методы (для AsyncAPIKeyRotator) ---

    async def before_request(self, request_info: 'RequestInfo') -> 'RequestInfo':
        """Async hook перед запросом"""
        return self.before_request_sync(request_info)

    async def after_request(self, response_info: 'ResponseInfo') -> 'ResponseInfo':
        """Async hook после ответа"""
        return self.after_request_sync(response_info)

    async def on_error(self, error_info: 'ErrorInfo') -> bool:
        """Async hook при ошибке"""
        return self.on_error_sync(error_info)

    # --- Sync методы (для APIKeyRotator) ---

    def before_request_sync(self, request_info: 'RequestInfo') -> 'RequestInfo':
        """Sync hook перед запросом"""
        return request_info

    def after_request_sync(self, response_info: 'ResponseInfo') -> 'ResponseInfo':
        """Sync hook после ответа"""
        return response_info

    def on_error_sync(self, error_info: 'ErrorInfo') -> bool:
        """Sync hook при ошибке"""
        return False