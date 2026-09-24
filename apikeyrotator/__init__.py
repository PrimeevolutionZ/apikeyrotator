"""
API Key Rotator - powerful library for API key rotation

Easy-to-use yet feature-rich API key rotator with support for:
- Multiple rotation strategies
- Secret providers (AWS, GCP, files, env)
- Middleware system
- Metrics and monitoring
- Automatic retry and error handling
- Circuit breaker, request deadlines, client-side key rate limits
- Shared state between processes (Redis)
- requests / aiohttp / httpx (HTTP/2) transports
"""

import logging as _logging


# Libraries must not configure logging output themselves: attach a NullHandler so
# nothing is printed unless the application configures logging (logging.basicConfig()).
_logging.getLogger(__name__).addHandler(_logging.NullHandler())

# Core
from .core import (
    APIKeyRotator,
    AsyncAPIKeyRotator,
    ConfigLoader,
    Headers,
    UnifiedResponse,
    parse_keys,
)
from .core.exceptions import (
    AllKeysExhaustedError,
    AllProvidersExhaustedError,
    APIKeyError,
    AuthenticationError,
    CircuitOpenError,
    DeadlineExceededError,
    HTTPStatusError,
    NoAPIKeysError,
)

# Metrics
from .metrics import (
    EndpointStats,
    PrometheusExporter,
    RotatorMetrics,
)

# Middleware
from .middleware import (
    CachingMiddleware,
    ErrorInfo,
    LoggingMiddleware,
    RateLimitMiddleware,
    RequestInfo,
    ResponseInfo,
    RotatorMiddleware,
)

# Providers
from .providers import (
    AWSSecretsManagerProvider,
    EnvironmentSecretProvider,
    FileSecretProvider,
    GCPSecretManagerProvider,
    SecretProvider,
    create_secret_provider,
)

# Router
from .router import FallbackRouter, ProviderRoute

# Shared state
from .state import InMemoryStateBackend, RedisStateBackend, StateBackend

# Strategies
from .strategies import (
    BaseRotationStrategy,
    FailoverRotationStrategy,
    HealthBasedStrategy,
    KeyMetrics,
    LRURotationStrategy,
    RandomRotationStrategy,
    RotationStrategy,
    RoundRobinRotationStrategy,
    WeightedRotationStrategy,
    create_rotation_strategy,
)

# Utils
from .utils import (
    CircuitBreaker,
    CircuitBreakerConfig,
    ErrorClassifier,
    ErrorType,
    async_retry_with_backoff,
    retry_with_backoff,
)


__version__ = "0.9.0"
__author__ = "Prime Evolution"

__all__ = [
    # Core
    "APIKeyRotator",
    "AsyncAPIKeyRotator",
    "APIKeyError",
    "NoAPIKeysError",
    "AllKeysExhaustedError",
    "AllProvidersExhaustedError",
    "HTTPStatusError",
    "DeadlineExceededError",
    "CircuitOpenError",
    "AuthenticationError",
    "parse_keys",
    "ConfigLoader",
    "UnifiedResponse",
    "Headers",

    # Strategies
    "RotationStrategy",
    "create_rotation_strategy",
    "BaseRotationStrategy",
    "RoundRobinRotationStrategy",
    "RandomRotationStrategy",
    "WeightedRotationStrategy",
    "LRURotationStrategy",
    "HealthBasedStrategy",
    "FailoverRotationStrategy",
    "KeyMetrics",

    # Providers
    "SecretProvider",
    "create_secret_provider",
    "EnvironmentSecretProvider",
    "FileSecretProvider",
    "AWSSecretsManagerProvider",
    "GCPSecretManagerProvider",

    # Middleware
    "RotatorMiddleware",
    "RequestInfo",
    "ResponseInfo",
    "ErrorInfo",
    "LoggingMiddleware",
    "CachingMiddleware",
    "RateLimitMiddleware",

    # Router
    "FallbackRouter",
    "ProviderRoute",

    # Shared state
    "StateBackend",
    "InMemoryStateBackend",
    "RedisStateBackend",

    # Metrics
    "RotatorMetrics",
    "EndpointStats",
    "PrometheusExporter",

    # Utils
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "ErrorClassifier",
    "ErrorType",
    "retry_with_backoff",
    "async_retry_with_backoff",
]