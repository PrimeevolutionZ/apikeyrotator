from .rotator import APIKeyRotator, AsyncAPIKeyRotator
from .exceptions import APIKeyError, NoAPIKeysError, AllKeysExhaustedError
from .rotation_strategies import (
    RotationStrategy,
    create_rotation_strategy,
    KeyMetrics,
    RoundRobinRotationStrategy,
    RandomRotationStrategy,
    WeightedRotationStrategy,
    LRURotationStrategy,
    HealthBasedStrategy,
    BaseRotationStrategy
)
from .secret_providers import (
    SecretProvider,
    EnvironmentSecretProvider,
    FileSecretProvider,
    AWSSecretsManagerProvider,
    create_secret_provider
)
from .metrics import RotatorMetrics, KeyStats, EndpointStats
from .middleware import (
    RotatorMiddleware,
    RequestInfo,
    ResponseInfo,
    ErrorInfo,
    RateLimitMiddleware,
    CachingMiddleware
)
from .error_classifier import ErrorClassifier, ErrorType
from .config_loader import ConfigLoader

__version__ = "0.3.1"
__author__ = "Prime Evolution"
__email__ = "develop@eclps-team.ru"

__all__ = [
    # Core classes
    'APIKeyRotator',
    'AsyncAPIKeyRotator',

    # Exceptions
    'APIKeyError',
    'NoAPIKeysError',
    'AllKeysExhaustedError',

    # Rotation strategies
    'RotationStrategy',
    'create_rotation_strategy',
    'KeyMetrics',
    'BaseRotationStrategy',
    'RoundRobinRotationStrategy',
    'RandomRotationStrategy',
    'WeightedRotationStrategy',
    'LRURotationStrategy',
    'HealthBasedStrategy',

    # Secret providers
    'SecretProvider',
    'EnvironmentSecretProvider',
    'FileSecretProvider',
    'AWSSecretsManagerProvider',
    'create_secret_provider',

    # Metrics
    'RotatorMetrics',
    'KeyStats',
    'EndpointStats',

    # Middleware
    'RotatorMiddleware',
    'RequestInfo',
    'ResponseInfo',
    'ErrorInfo',
    'RateLimitMiddleware',
    'CachingMiddleware',

    # Utilities
    'ErrorClassifier',
    'ErrorType',
    'ConfigLoader',
]