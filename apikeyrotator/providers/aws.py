"""Провайдер секретов из AWS Secrets Manager"""

import json
from typing import List


class AWSSecretsManagerProvider:
    """
    Провайдер секретов из AWS Secrets Manager.

    Требует установки: pip install boto3

    Секрет может быть в форматах:
    - JSON массив: ["key1", "key2"]
    - JSON объект: {"keys": ["key1", "key2"]} или {"api_keys": ["key1", "key2"]}
    - JSON строка: "key1,key2,key3"
    - Простая строка: key1,key2,key3
    """

    def __init__(self, secret_name: str, region_name: str = 'us-east-1'):
        self.secret_name = secret_name
        self.region_name = region_name
        self._client = None

    def _get_client(self):
        """Создает или возвращает boto3 клиент"""
        try:
            import boto3
        except ImportError:
            raise ImportError(
                "boto3 is not installed. "
                "Install it with: pip install boto3"
            )

        if self._client is None:
            self._client = boto3.client(
                'secretsmanager',
                region_name=self.region_name
            )
        return self._client

    async def get_keys(self) -> List[str]:
        client = self._get_client()

        try:
            response = client.get_secret_value(SecretId=self.secret_name)

            if 'SecretString' in response:
                secret = response['SecretString']

                # Попытка парсинга как JSON
                try:
                    keys_data = json.loads(secret)

                    if isinstance(keys_data, list):
                        return [str(k).strip() for k in keys_data if str(k).strip()]
                    elif isinstance(keys_data, dict):
                        # Извлекаем из ключей 'keys' или 'api_keys'
                        keys_list = keys_data.get('keys') or keys_data.get('api_keys')

                        if keys_list is None:
                            keys_list = list(keys_data.values())

                        if isinstance(keys_list, list):
                            return [str(k).strip() for k in keys_list if str(k).strip()]
                        elif isinstance(keys_list, str):
                            return [k.strip() for k in keys_list.split(',') if k.strip()]
                    elif isinstance(keys_data, str):
                        return [k.strip() for k in keys_data.split(',') if k.strip()]

                except json.JSONDecodeError:
                    # Не JSON - парсим как CSV
                    return [k.strip() for k in secret.split(',') if k.strip()]

            return []

        except client.exceptions.ResourceNotFoundException:
            print(f"Secret {self.secret_name} not found in AWS Secrets Manager.")
            return []
        except Exception as e:
            print(f"Error retrieving secret {self.secret_name}: {e}")
            return []

    async def refresh_keys(self) -> List[str]:
        return await self.get_keys()