"""Фабрика для создания провайдеров секретов"""

from typing import Union
from .base import SecretProvider
from .environment import EnvironmentSecretProvider
from .file import FileSecretProvider
from .aws import AWSSecretsManagerProvider
from .gcp import GCPSecretManagerProvider


def create_secret_provider(provider_type: str, **kwargs) -> SecretProvider:
    """
    Фабричная функция для создания провайдера секретов.

    Args:
        provider_type: Тип провайдера
        **kwargs: Параметры для конкретного провайдера

    Returns:
        SecretProvider: Экземпляр провайдера

    Examples:
        >>> # Environment
        >>> provider = create_secret_provider('env', env_var='MY_KEYS')

        >>> # File
        >>> provider = create_secret_provider('file', file_path='keys.txt')

        >>> # AWS
        >>> provider = create_secret_provider(
        ...     'aws_secrets_manager',
        ...     secret_name='my-keys',
        ...     region_name='us-east-1'
        ... )

        >>> # GCP
        >>> provider = create_secret_provider(
        ...     'gcp_secret_manager',
        ...     project_id='my-project',
        ...     secret_id='api-keys'
        ... )
    """
    provider_type = provider_type.lower()

    if provider_type in ("env", "environment"):
        return EnvironmentSecretProvider(**kwargs)
    elif provider_type == "file":
        return FileSecretProvider(**kwargs)
    elif provider_type in ("aws_secrets_manager", "aws"):
        return AWSSecretsManagerProvider(**kwargs)
    elif provider_type in ("gcp_secret_manager", "gcp"):
        return GCPSecretManagerProvider(**kwargs)
    else:
        raise ValueError(
            f"Unknown secret provider type: {provider_type}. "
            f"Supported: 'env', 'file', 'aws_secrets_manager', 'gcp_secret_manager'"
        )