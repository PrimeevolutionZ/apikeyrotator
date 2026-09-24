"""
Base protocol for secret providers
"""

import json
from typing import Any, Protocol


def _split_csv(value: str) -> list[str]:
    return [k.strip() for k in value.replace('\n', ',').split(',') if k.strip()]


def parse_secret_payload(secret: str) -> list[str]:
    """
    Parses a secret payload into a list of keys.

    Supported formats:
    - JSON array: ["key1", "key2"]
    - JSON object: {"keys": [...]} / {"api_keys": [...]} / {"name": "key", ...}
    - JSON string: "key1,key2"
    - Plain string: key1,key2 (commas and/or newlines)
    """
    try:
        data: Any = json.loads(secret)
    except (json.JSONDecodeError, TypeError, ValueError):
        return _split_csv(secret or "")

    if isinstance(data, dict):
        data = data.get('keys') or data.get('api_keys') or list(data.values())
    if isinstance(data, list):
        return [str(k).strip() for k in data if k is not None and str(k).strip()]
    if isinstance(data, str):
        return _split_csv(data)
    return []


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

    async def get_keys(self) -> list[str]:
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

    async def refresh_keys(self) -> list[str]:
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