import os
from typing import List, Protocol, Optional
import json


class SecretProvider(Protocol):
    """
    Протокол для провайдеров секретов.

    Определяет интерфейс для загрузки API ключей из различных источников:
    - Переменные окружения
    - Файлы
    - Облачные хранилища секретов (AWS, GCP, Azure)
    - Системы управления секретами (Vault, etc.)
    """

    async def get_keys(self) -> List[str]:
        """
        Асинхронно получает список API ключей.

        Returns:
            List[str]: Список API ключей
        """
        ...

    async def refresh_keys(self) -> List[str]:
        """
        Асинхронно обновляет список API ключей.

        Полезно для ротации ключей и получения обновлённых значений.

        Returns:
            List[str]: Обновлённый список API ключей
        """
        ...


class EnvironmentSecretProvider:
    """
    Провайдер секретов из переменных окружения.

    Загружает API ключи из переменной окружения.
    Поддерживает формат: key1,key2,key3

    Example:
        >>> import os
        >>> os.environ["API_KEYS"] = "key1,key2,key3"
        >>> provider = EnvironmentSecretProvider("API_KEYS")
        >>> keys = await provider.get_keys()
        >>> print(keys)
        ['key1', 'key2', 'key3']
    """

    def __init__(self, env_var: str = "API_KEYS"):
        """
        Инициализирует провайдер.

        Args:
            env_var: Имя переменной окружения (по умолчанию "API_KEYS")
        """
        self.env_var = env_var

    async def get_keys(self) -> List[str]:
        """
        Получает ключи из переменной окружения.

        Returns:
            List[str]: Список API ключей или пустой список
        """
        keys_str = os.getenv(self.env_var)
        if not keys_str:
            return []
        return [k.strip() for k in keys_str.split(",") if k.strip()]

    async def refresh_keys(self) -> List[str]:
        """
        Обновляет ключи из переменной окружения.

        Returns:
            List[str]: Обновлённый список API ключей
        """
        return await self.get_keys()


class FileSecretProvider:
    """
    Провайдер секретов из файла.

    Загружает API ключи из текстового файла.
    Поддерживает форматы:
    - Строка через запятую: key1,key2,key3
    - По одному ключу на строку

    Example:
        >>> # Создаём файл с ключами
        >>> with open('keys.txt', 'w') as f:
        ...     f.write('key1,key2,key3')
        >>> provider = FileSecretProvider('keys.txt')
        >>> keys = await provider.get_keys()
        >>> print(keys)
        ['key1', 'key2', 'key3']
    """

    def __init__(self, file_path: str):
        """
        Инициализирует провайдер.

        Args:
            file_path: Путь к файлу с ключами
        """
        self.file_path = file_path

    async def get_keys(self) -> List[str]:
        """
        Загружает ключи из файла.

        Returns:
            List[str]: Список API ключей или пустой список
        """
        if not os.path.exists(self.file_path):
            return []

        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Попробуем парсить как JSON массив
            try:
                keys = json.loads(content)
                if isinstance(keys, list):
                    return [str(k).strip() for k in keys if k]
            except json.JSONDecodeError:
                pass

            # Парсим как CSV или построчно
            if ',' in content:
                # CSV формат
                return [k.strip() for k in content.split(",") if k.strip()]
            else:
                # Построчный формат
                return [k.strip() for k in content.split("\n") if k.strip()]
        except Exception as e:
            print(f"Error reading keys from {self.file_path}: {e}")
            return []

    async def refresh_keys(self) -> List[str]:
        """
        Обновляет ключи из файла.

        Returns:
            List[str]: Обновлённый список API ключей
        """
        return await self.get_keys()


class AWSSecretsManagerProvider:
    """
    Провайдер секретов из AWS Secrets Manager.

    Загружает API ключи из AWS Secrets Manager.
    Требует установки boto3: pip install boto3

    Секрет должен быть в одном из форматов:
    - JSON массив: ["key1", "key2", "key3"]
    - JSON строка: "key1,key2,key3"
    - Простая строка: key1,key2,key3

    Example:
        >>> provider = AWSSecretsManagerProvider(
        ...     secret_name="my-api-keys",
        ...     region_name="us-east-1"
        ... )
        >>> keys = await provider.get_keys()
    """

    def __init__(self, secret_name: str, region_name: str = 'us-east-1'):
        """
        Инициализирует провайдер.

        Args:
            secret_name: Имя секрета в AWS Secrets Manager
            region_name: AWS регион (по умолчанию 'us-east-1')

        Raises:
            ImportError: Если boto3 не установлен
        """
        self.secret_name = secret_name
        self.region_name = region_name
        self._client = None

    def _get_client(self):
        """
        Создаёт или возвращает существующий boto3 клиент.

        Returns:
            boto3.client: Клиент AWS Secrets Manager

        Raises:
            ImportError: Если boto3 не установлен
        """
        try:
            import boto3
        except ImportError:
            raise ImportError(
                "boto3 is not installed. "
                "Please install it with `pip install boto3` to use AWSSecretsManagerProvider."
            )

        if self._client is None:
            self._client = boto3.client('secretsmanager', region_name=self.region_name)
        return self._client

    async def get_keys(self) -> List[str]:
        """
        Загружает ключи из AWS Secrets Manager.

        Returns:
            List[str]: Список API ключей или пустой список
        """
        client = self._get_client()

        try:
            response = client.get_secret_value(SecretId=self.secret_name)

            if 'SecretString' in response:
                secret = response['SecretString']

                # Попытка парсинга как JSON
                try:
                    keys_data = json.loads(secret)

                    if isinstance(keys_data, list):
                        # JSON массив ключей
                        return [str(k).strip() for k in keys_data if str(k).strip()]
                    elif isinstance(keys_data, dict):
                        # JSON объект - извлекаем значение по ключу 'keys' или 'api_keys'
                        if 'keys' in keys_data:
                            keys_list = keys_data['keys']
                        elif 'api_keys' in keys_data:
                            keys_list = keys_data['api_keys']
                        else:
                            # Берём все значения из словаря
                            keys_list = list(keys_data.values())

                        if isinstance(keys_list, list):
                            return [str(k).strip() for k in keys_list if str(k).strip()]
                        elif isinstance(keys_list, str):
                            return [k.strip() for k in keys_list.split(',') if k.strip()]
                    elif isinstance(keys_data, str):
                        # JSON строка с ключами через запятую
                        return [k.strip() for k in keys_data.split(',') if k.strip()]

                except json.JSONDecodeError:
                    # Не JSON - парсим как CSV
                    return [k.strip() for k in secret.split(',') if k.strip()]

            return []

        except client.exceptions.ResourceNotFoundException:
            print(f"Secret {self.secret_name} not found in AWS Secrets Manager.")
            return []
        except Exception as e:
            print(f"Error retrieving secret {self.secret_name} from AWS: {e}")
            return []

    async def refresh_keys(self) -> List[str]:
        """
        Обновляет ключи из AWS Secrets Manager.

        Returns:
            List[str]: Обновлённый список API ключей
        """
        return await self.get_keys()


class GCPSecretManagerProvider:
    """
    Провайдер секретов из Google Cloud Secret Manager.

    Загружает API ключи из GCP Secret Manager.
    Требует установки google-cloud-secret-manager:
    pip install google-cloud-secret-manager

    Example:
        >>> provider = GCPSecretManagerProvider(
        ...     project_id="my-project",
        ...     secret_id="api-keys"
        ... )
        >>> keys = await provider.get_keys()
    """

    def __init__(self, project_id: str, secret_id: str, version_id: str = "latest"):
        """
        Инициализирует провайдер.

        Args:
            project_id: ID проекта GCP
            secret_id: ID секрета
            version_id: Версия секрета (по умолчанию "latest")

        Raises:
            ImportError: Если google-cloud-secret-manager не установлен
        """
        self.project_id = project_id
        self.secret_id = secret_id
        self.version_id = version_id
        self._client = None

    async def _get_client(self):
        """Создаёт или возвращает существующий GCP клиент."""
        try:
            from google.cloud import secretmanager
        except ImportError:
            raise ImportError(
                "google-cloud-secret-manager is not installed. "
                "Please install it with `pip install google-cloud-secret-manager`"
            )

        if self._client is None:
            self._client = secretmanager.SecretManagerServiceClient()
        return self._client

    async def get_keys(self) -> List[str]:
        """
        Загружает ключи из GCP Secret Manager.

        Returns:
            List[str]: Список API ключей или пустой список
        """
        client = await self._get_client()

        try:
            name = f"projects/{self.project_id}/secrets/{self.secret_id}/versions/{self.version_id}"
            response = client.access_secret_version(request={"name": name})
            secret_string = response.payload.data.decode('UTF-8')

            # Парсинг аналогично AWS
            try:
                keys_data = json.loads(secret_string)
                if isinstance(keys_data, list):
                    return [str(k).strip() for k in keys_data if str(k).strip()]
                elif isinstance(keys_data, str):
                    return [k.strip() for k in keys_data.split(',') if k.strip()]
            except json.JSONDecodeError:
                return [k.strip() for k in secret_string.split(',') if k.strip()]

            return []

        except Exception as e:
            print(f"Error retrieving secret from GCP: {e}")
            return []

    async def refresh_keys(self) -> List[str]:
        """
        Обновляет ключи из GCP Secret Manager.

        Returns:
            List[str]: Обновлённый список API ключей
        """
        return await self.get_keys()


def create_secret_provider(provider_type: str, **kwargs) -> SecretProvider:
    """
    Фабричная функция для создания провайдера секретов.

    Args:
        provider_type: Тип провайдера ('env', 'file', 'aws_secrets_manager', 'gcp_secret_manager')
        **kwargs: Параметры для конкретного провайдера

    Returns:
        SecretProvider: Экземпляр провайдера секретов

    Raises:
        ValueError: Если тип провайдера неизвестен

    Examples:
        >>> # Environment provider
        >>> provider = create_secret_provider('env', env_var='MY_KEYS')

        >>> # File provider
        >>> provider = create_secret_provider('file', file_path='keys.txt')

        >>> # AWS provider
        >>> provider = create_secret_provider(
        ...     'aws_secrets_manager',
        ...     secret_name='my-keys',
        ...     region_name='us-east-1'
        ... )

        >>> # GCP provider
        >>> provider = create_secret_provider(
        ...     'gcp_secret_manager',
        ...     project_id='my-project',
        ...     secret_id='api-keys'
        ... )
    """
    provider_type = provider_type.lower()

    if provider_type == "env" or provider_type == "environment":
        return EnvironmentSecretProvider(**kwargs)
    elif provider_type == "file":
        return FileSecretProvider(**kwargs)
    elif provider_type == "aws_secrets_manager" or provider_type == "aws":
        return AWSSecretsManagerProvider(**kwargs)
    elif provider_type == "gcp_secret_manager" or provider_type == "gcp":
        return GCPSecretManagerProvider(**kwargs)
    else:
        raise ValueError(
            f"Unknown secret provider type: {provider_type}. "
            f"Supported types: 'env', 'file', 'aws_secrets_manager', 'gcp_secret_manager'"
        )