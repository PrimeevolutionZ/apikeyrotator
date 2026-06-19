class APIKeyError(Exception):
    """Base exception for API key errors"""
    pass

class NoAPIKeysError(APIKeyError):
    """No API keys found"""
    pass

class AllKeysExhaustedError(APIKeyError):
    """All keys are exhausted"""
    pass

class AllProvidersExhaustedError(APIKeyError):
    """All providers (and their keys) are exhausted"""
    pass