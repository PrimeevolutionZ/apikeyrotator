"""
Providers пакет - провайдеры секретов для загрузки API ключей
"""

from .base import SecretProvider
from .environment import EnvironmentSecretProvider
from .file import FileSecretProvider
from .aws import AWSSecretsManagerProvider
from .factory import create_secret_provider

# Опциональный GCP провайдер
try:
    from .gcp import GCPSecretManagerProvider
    _HAS_GCP = True
except ImportError:
    _HAS_GCP = False

__all__ = [
    "SecretProvider",
    "EnvironmentSecretProvider",
    "FileSecretProvider",
    "AWSSecretsManagerProvider",
    "create_secret_provider",
]

if _HAS_GCP:
    __all__.append("GCPSecretManagerProvider")