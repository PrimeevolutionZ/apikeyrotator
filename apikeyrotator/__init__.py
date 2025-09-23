from .rotator import APIKeyRotator, AsyncAPIKeyRotator
from .exceptions import APIKeyError, NoAPIKeysError, AllKeysExhaustedError
from .rotation_strategies import RotationStrategy, create_rotation_strategy, KeyMetrics
from .secret_providers import SecretProvider, EnvironmentSecretProvider, FileSecretProvider, AWSSecretsManagerProvider, create_secret_provider
from .metrics import RotatorMetrics, KeyStats, EndpointStats
from .middleware import RotatorMiddleware, RequestInfo, ResponseInfo, ErrorInfo, RateLimitMiddleware, CachingMiddleware

__version__ = "0.1.2" # Incrementing version due to new features
__author__ = "Prime Evolution"
__email__ = "develop@eclps-team.ru"

__all__ = [
    'APIKeyRotator',
    'AsyncAPIKeyRotator',
    'APIKeyError',
    'NoAPIKeysError',
    'AllKeysExhaustedError',
    'RotationStrategy',
    'create_rotation_strategy',
    'KeyMetrics',
    'SecretProvider',
    'EnvironmentSecretProvider',
    'FileSecretProvider',
    'AWSSecretsManagerProvider',
    'create_secret_provider',
    'RotatorMetrics',
    'KeyStats',
    'EndpointStats',
    'RotatorMiddleware',
    'RequestInfo',
    'ResponseInfo',
    'ErrorInfo',
    'RateLimitMiddleware',
    'CachingMiddleware',
]


