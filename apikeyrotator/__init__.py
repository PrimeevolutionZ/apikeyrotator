"""
API Key Rotator - powerful library for API key rotation

Easy-to-use yet feature-rich API key rotator with support for:
- Multiple rotation strategies
- Secret providers (AWS, GCP, files, env)
- Middleware system
- Metrics and monitoring
- Automatic retry and error handling
"""

# Core
from .core import (
    APIKeyRotator,
    AsyncAPIKeyRotator,
    APIKeyError,
    NoAPIKeysError,
    AllKeysExhaustedError,
    parse_keys,
    ConfigLoader,
)

# Strategies
from .strategies import (
    RotationStrategy,
    create_rotation_strategy,
    BaseRotationStrategy,
    RoundRobinRotationStrategy,
    RandomRotationStrategy,
    WeightedRotationStrategy,
    LRURotationStrategy,
    HealthBasedStrategy,
    KeyMetrics,
)

# Providers
from .providers import (
    SecretProvider,
    create_secret_provider,
    EnvironmentSecretProvider,
    FileSecretProvider,
    AWSSecretsManagerProvider,
)

# Middleware
from .middleware import (
    RotatorMiddleware,
    RequestInfo,
    ResponseInfo,
    ErrorInfo,
    LoggingMiddleware,
    CachingMiddleware,
    RateLimitMiddleware,
    RetryMiddleware,
)

# Metrics
from .metrics import (
    RotatorMetrics,
    EndpointStats,
    PrometheusExporter,
)

# Utils
from .utils import (
    ErrorClassifier,
    ErrorType,
    retry_with_backoff,
    async_retry_with_backoff,
)

__version__ = "0.4.3"
__author__ = "Prime Evolution"
__email__ = "develop@eclps-team.ru"

__all__ = [
    # Core
    "APIKeyRotator",
    "AsyncAPIKeyRotator",
    "APIKeyError",
    "NoAPIKeysError",
    "AllKeysExhaustedError",
    "parse_keys",
    "ConfigLoader",

    # Strategies
    "RotationStrategy",
    "create_rotation_strategy",
    "BaseRotationStrategy",
    "RoundRobinRotationStrategy",
    "RandomRotationStrategy",
    "WeightedRotationStrategy",
    "LRURotationStrategy",
    "HealthBasedStrategy",
    "KeyMetrics",

    # Providers
    "SecretProvider",
    "create_secret_provider",
    "EnvironmentSecretProvider",
    "FileSecretProvider",
    "AWSSecretsManagerProvider",

    # Middleware
    "RotatorMiddleware",
    "RequestInfo",
    "ResponseInfo",
    "ErrorInfo",
    "LoggingMiddleware",
    "CachingMiddleware",
    "RateLimitMiddleware",
    "RetryMiddleware",

    # Metrics
    "RotatorMetrics",
    "EndpointStats",
    "PrometheusExporter",

    # Utils
    "ErrorClassifier",
    "ErrorType",
    "retry_with_backoff",
    "async_retry_with_backoff",
]