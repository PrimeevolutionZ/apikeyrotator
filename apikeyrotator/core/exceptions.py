class APIKeyError(Exception):
    """Base exception for API key errors"""
    pass

class NoAPIKeysError(APIKeyError):
    """No API keys found"""
    pass

class AllKeysExhaustedError(APIKeyError):
    """All keys are exhausted"""
    pass