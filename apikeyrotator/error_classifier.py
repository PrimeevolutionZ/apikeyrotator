from enum import Enum
from typing import Optional, Union
import requests


class ErrorType(Enum):
    """
    Типы ошибок для классификации HTTP запросов.

    Attributes:
        RATE_LIMIT: Превышен лимит запросов (429)
        TEMPORARY: Временная ошибка сервера (5xx)
        PERMANENT: Постоянная ошибка (401, 403, 4xx)
        NETWORK: Проблемы с сетью или соединением
        UNKNOWN: Неизвестный тип ошибки
    """
    RATE_LIMIT = "rate_limit"
    TEMPORARY = "temporary"
    PERMANENT = "permanent"
    NETWORK = "network"
    UNKNOWN = "unknown"


class ErrorClassifier:
    """
    Классификатор ошибок HTTP запросов.

    Определяет тип ошибки для принятия решения о необходимости retry
    и переключения ключей API.
    """

    def classify_error(
            self,
            response: Optional[requests.Response] = None,
            exception: Optional[Exception] = None
    ) -> ErrorType:
        """
        Классифицирует ошибки для принятия решения о retry.

        Логика классификации:
        - RATE_LIMIT (429): нужно переключить ключ
        - TEMPORARY (5xx): можно повторить с тем же ключом
        - PERMANENT (401, 403, 4xx): ключ неработоспособен, нужно удалить
        - NETWORK: проблемы с сетью/прокси, можно повторить
        - UNKNOWN: неизвестная ошибка

        Args:
            response: HTTP ответ от сервера (опционально)
            exception: Исключение, возникшее при запросе (опционально)

        Returns:
            ErrorType: Тип классифицированной ошибки

        Examples:
            >>> classifier = ErrorClassifier()
            >>> # Классификация по ответу
            >>> error_type = classifier.classify_error(response=response_obj)
            >>> # Классификация по исключению
            >>> error_type = classifier.classify_error(exception=connection_error)
        """
        # Классификация исключений
        if exception:
            if isinstance(exception, (requests.exceptions.ConnectionError,
                                      requests.exceptions.Timeout)):
                return ErrorType.NETWORK
            return ErrorType.UNKNOWN

        # Если нет ответа, возвращаем UNKNOWN
        if response is None:
            return ErrorType.UNKNOWN

        status_code = response.status_code

        # Классификация по статус коду
        if status_code == 429:
            # Too Many Requests - Rate Limit
            return ErrorType.RATE_LIMIT
        elif status_code in [500, 502, 503, 504]:
            # Server errors - часто временные
            return ErrorType.TEMPORARY
        elif status_code in [401, 403]:
            # Unauthorized, Forbidden - проблема с ключом
            return ErrorType.PERMANENT
        elif 400 <= status_code < 500:
            # Другие клиентские ошибки - считаем постоянными
            return ErrorType.PERMANENT

        return ErrorType.UNKNOWN

    def is_retryable(
            self,
            response: Optional[requests.Response] = None,
            exception: Optional[Exception] = None
    ) -> bool:
        """
        Определяет, можно ли повторить запрос.

        Args:
            response: HTTP ответ от сервера (опционально)
            exception: Исключение, возникшее при запросе (опционально)

        Returns:
            bool: True если запрос можно повторить, False иначе
        """
        error_type = self.classify_error(response, exception)
        return error_type in [ErrorType.RATE_LIMIT, ErrorType.TEMPORARY, ErrorType.NETWORK]

    def should_switch_key(
            self,
            response: Optional[requests.Response] = None,
            exception: Optional[Exception] = None
    ) -> bool:
        """
        Определяет, нужно ли переключить API ключ.

        Args:
            response: HTTP ответ от сервера (опционально)
            exception: Исключение, возникшее при запросе (опционально)

        Returns:
            bool: True если нужно переключить ключ, False иначе
        """
        error_type = self.classify_error(response, exception)
        return error_type in [ErrorType.RATE_LIMIT, ErrorType.PERMANENT]

    def should_remove_key(
            self,
            response: Optional[requests.Response] = None,
            exception: Optional[Exception] = None
    ) -> bool:
        """
        Определяет, нужно ли удалить API ключ из ротации.

        Args:
            response: HTTP ответ от сервера (опционально)
            exception: Исключение, возникшее при запросе (опционально)

        Returns:
            bool: True если ключ нужно удалить, False иначе
        """
        error_type = self.classify_error(response, exception)
        return error_type == ErrorType.PERMANENT