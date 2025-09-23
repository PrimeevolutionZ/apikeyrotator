from enum import Enum
from typing import Optional, Union
import requests

class ErrorType(Enum):
    RATE_LIMIT = "rate_limit"
    TEMPORARY = "temporary"
    PERMANENT = "permanent"
    NETWORK = "network"
    UNKNOWN = "unknown"

class ErrorClassifier:
    def classify_error(self, response: Optional[requests.Response] = None, 
                      exception: Optional[Exception] = None) -> ErrorType:
        """
        Классифицирует ошибки для принятия решения о ретрае:
        - RATE_LIMIT: нужно переключить ключ
        - TEMPORARY: можно повторить с тем же ключом
        - PERMANENT: ключ неработоспособен
        - NETWORK: проблемы с сетью/прокси
        """
        if exception:
            if isinstance(exception, requests.exceptions.ConnectionError) or \
               isinstance(exception, requests.exceptions.Timeout):
                return ErrorType.NETWORK
            return ErrorType.UNKNOWN

        if response is None:
            return ErrorType.UNKNOWN

        status_code = response.status_code

        if status_code == 429: # Too Many Requests
            return ErrorType.RATE_LIMIT
        elif status_code in [500, 502, 503, 504]: # Server errors, often temporary
            return ErrorType.TEMPORARY
        elif status_code in [401, 403]: # Unauthorized, Forbidden - likely permanent key issue
            return ErrorType.PERMANENT
        elif status_code >= 400 and status_code < 500: # Other client errors
            return ErrorType.PERMANENT # Treat as permanent for key rotation purposes
        
        return ErrorType.UNKNOWN


