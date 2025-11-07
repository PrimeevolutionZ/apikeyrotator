"""Базовый протокол для middleware"""

from typing import Protocol
from .models import RequestInfo, ResponseInfo, ErrorInfo


class RotatorMiddleware(Protocol):
    """
    Протокол для middleware ротатора.

    Middleware позволяет перехватывать и модифицировать запросы,
    ответы и обрабатывать ошибки.
    """

    async def before_request(self, request_info: RequestInfo) -> RequestInfo:
        """Вызывается перед отправкой запроса"""
        return request_info

    async def after_request(self, response_info: ResponseInfo) -> ResponseInfo:
        """Вызывается после успешного ответа"""
        return response_info

    async def on_error(self, error_info: ErrorInfo) -> bool:
        """
        Вызывается при ошибке.

        Returns:
            bool: True если ошибка обработана, False для пробрасывания
        """
        return False

