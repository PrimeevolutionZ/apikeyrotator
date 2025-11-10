"""
API Key Rotator - мощная библиотека для ротации API ключей

Простой в использовании, но feature-rich ротатор API ключей с поддержкой:
- Множественных стратегий ротации
- Провайдеров секретов (AWS, GCP, файлы, env)
- Middleware системы
- Метрик и мониторинга
- Автоматического retry и обработки ошибок
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
    KeyStats,
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

__version__ = "0.4.1"
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
    "KeyStats",
    "EndpointStats",
    "PrometheusExporter",

    # Utils
    "ErrorClassifier",
    "ErrorType",
    "retry_with_backoff",
    "async_retry_with_backoff",
]