class APIKeyError(Exception):
    """Базовое исключение для ошибок API ключей"""
    pass

class NoAPIKeysError(APIKeyError):
    """Не найдено ни одного API ключа"""
    pass

class AllKeysExhaustedError(APIKeyError):
    """Все ключи исчерпаны"""
    pass
