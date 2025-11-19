"""
Base protocol for secret providers
"""

from typing import List, Protocol


class SecretProvider(Protocol):
    """
    Protocol for secret providers.

    Defines the interface for loading API keys from various sources:
    - Environment variables
    - Files
    - Cloud secret stores (AWS Secrets Manager, GCP Secret Manager, Azure Key Vault)
    - Secret management systems (HashiCorp Vault, etc.)

    All providers must implement two asynchronous methods:
    - get_keys(): For initial key loading
    - refresh_keys(): For key refresh (rotation, expiration)
    """

    async def get_keys(self) -> List[str]:
        """
        Asynchronously retrieves a list of API keys.

        Returns:
            List[str]: List of API keys

        Example:
            >>> provider = EnvironmentSecretProvider("API_KEYS")
            >>> keys = await provider.get_keys()
            >>> print(keys)
            ['key1', 'key2', 'key3']
        """
        ...

    async def refresh_keys(self) -> List[str]:
        """
        Asynchronously refreshes the list of API keys.

        Useful for:
        - Key rotation
        - Fetching updated values from storage
        - Refreshing upon expiration

        Returns:
            List[str]: Updated list of API keys

        Example:
            >>> provider = AWSSecretsManagerProvider("my-api-keys")
            >>> new_keys = await provider.refresh_keys()
            >>> print(f"Loaded {len(new_keys)} keys")
        """
        ...