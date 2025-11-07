"""
Базовый протокол для провайдеров секретов
"""

from typing import List, Protocol


class SecretProvider(Protocol):
    """
    Протокол для провайдеров секретов.

    Определяет интерфейс для загрузки API ключей из различных источников:
    - Переменные окружения
    - Файлы
    - Облачные хранилища секретов (AWS Secrets Manager, GCP Secret Manager, Azure Key Vault)
    - Системы управления секретами (HashiCorp Vault, etc.)

    Все провайдеры должны реализовывать два асинхронных метода:
    - get_keys(): Для первоначальной загрузки ключей
    - refresh_keys(): Для обновления ключей (ротация, истечение срока действия)
    """

    async def get_keys(self) -> List[str]:
        """
        Асинхронно получает список API ключей.

        Returns:
            List[str]: Список API ключей

        Example:
            >>> provider = EnvironmentSecretProvider("API_KEYS")
            >>> keys = await provider.get_keys()
            >>> print(keys)
            ['key1', 'key2', 'key3']
        """
        ...

    async def refresh_keys(self) -> List[str]:
        """
        Асинхронно обновляет список API ключей.

        Полезно для:
        - Ротации ключей
        - Получения обновлённых значений из хранилища
        - Обновления при истечении срока действия

        Returns:
            List[str]: Обновлённый список API ключей

        Example:
            >>> provider = AWSSecretsManagerProvider("my-api-keys")
            >>> new_keys = await provider.refresh_keys()
            >>> print(f"Loaded {len(new_keys)} keys")
        """
        ...