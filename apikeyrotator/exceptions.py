class APIKeyExhaustedError(Exception):
    """Все ключи исчерпаны, запрос не удался"""
    pass


class NoAPIKeysError(Exception):
    """Не найдено ни одного API-ключа в .env"""
    pass


class APIRequestFailedError(Exception):
    """Запрос не удался даже после всех попыток"""
    def __init__(self, message: str, last_response=None):
        super().__init__(message)
        self.last_response = last_response