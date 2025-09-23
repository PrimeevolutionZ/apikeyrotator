import os
from typing import List, Protocol, Optional
import json

class SecretProvider(Protocol):
    async def get_keys(self) -> List[str]:
        """Асинхронно получает список API ключей."""
        pass

    async def refresh_keys(self) -> List[str]:
        """Асинхронно обновляет список API ключей."""
        pass

class EnvironmentSecretProvider(SecretProvider):
    def __init__(self, env_var: str = "API_KEYS"):
        self.env_var = env_var

    async def get_keys(self) -> List[str]:
        keys_str = os.getenv(self.env_var)
        if not keys_str:
            return []
        return [k.strip() for k in keys_str.split(",") if k.strip()]

    async def refresh_keys(self) -> List[str]:
        return await self.get_keys()

class FileSecretProvider(SecretProvider):
    def __init__(self, file_path: str):
        self.file_path = file_path

    async def get_keys(self) -> List[str]:
        if not os.path.exists(self.file_path):
            return []
        with open(self.file_path, 'r') as f:
            content = f.read()
        return [k.strip() for k in content.split(",") if k.strip()]

    async def refresh_keys(self) -> List[str]:
        return await self.get_keys()

# Example for AWS Secrets Manager (requires boto3 and aiobotocore)
# For simplicity, this example uses a synchronous boto3 client, but in a real async app,
# you'd use aiobotocore or run in a thread pool.
class AWSSecretsManagerProvider(SecretProvider):
    def __init__(self, secret_name: str, region_name: str = 'us-east-1'):
        self.secret_name = secret_name
        self.region_name = region_name
        self._client = None

    async def _get_client(self):
        # Lazy import and client creation to avoid dependency issues if not used
        try:
            import boto3
        except ImportError:
            raise ImportError("boto3 is not installed. Please install it with `pip install boto3` to use AWSSecretsManagerProvider.")
        if self._client is None:
            self._client = boto3.client('secretsmanager', region_name=self.region_name)
        return self._client

    async def get_keys(self) -> List[str]:
        client = await self._get_client()
        try:
            get_secret_value_response = client.get_secret_value(SecretId=self.secret_name)
            if 'SecretString' in get_secret_value_response:
                secret = get_secret_value_response['SecretString']
                # Assuming the secret is a comma-separated string or JSON array of keys
                try:
                    keys_data = json.loads(secret)
                    if isinstance(keys_data, list):
                        return [str(k).strip() for k in keys_data if str(k).strip()]
                    elif isinstance(keys_data, str):
                        return [k.strip() for k in keys_data.split(',') if k.strip()]
                except json.JSONDecodeError:
                    return [k.strip() for k in secret.split(',') if k.strip()]
            return []
        except client.exceptions.ResourceNotFoundException:
            print(f"Secret {self.secret_name} not found.")
            return []
        except Exception as e:
            print(f"Error retrieving secret {self.secret_name}: {e}")
            return []

    async def refresh_keys(self) -> List[str]:
        return await self.get_keys()

# Factory function to create secret providers
def create_secret_provider(provider_type: str, **kwargs) -> SecretProvider:
    if provider_type == "env":
        return EnvironmentSecretProvider(**kwargs)
    elif provider_type == "file":
        return FileSecretProvider(**kwargs)
    elif provider_type == "aws_secrets_manager":
        return AWSSecretsManagerProvider(**kwargs)
    # Add other providers here
    else:
        raise ValueError(f"Unknown secret provider type: {provider_type}")


