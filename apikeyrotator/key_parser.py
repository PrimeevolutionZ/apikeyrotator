import os
from typing import List, Optional, Union
import logging
from .exceptions import NoAPIKeysError


def _setup_default_logger():
    """
    Создает и настраивает логгер по умолчанию.

    Returns:
        logging.Logger: Настроенный логгер
    """
    logger = logging.getLogger(__name__)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def parse_keys(
        api_keys: Optional[Union[List[str], str]] = None,
        env_var: str = "API_KEYS",
        logger: Optional[logging.Logger] = None
) -> List[str]:
    """
    Умный парсер API ключей из различных источников.

    Поддерживает загрузку ключей:
    1. Напрямую через параметр api_keys (список или строка через запятую)
    2. Из переменной окружения
    3. Из .env файла (если используется python-dotenv)

    Args:
        api_keys: Ключи в виде списка или строки через запятую.
                 Если None, пытается загрузить из переменной окружения.
        env_var: Имя переменной окружения для загрузки ключей.
                По умолчанию "API_KEYS".
        logger: Логгер для вывода сообщений. Если None, создается новый.

    Returns:
        List[str]: Список валидных API ключей (без пустых строк и пробелов)

    Raises:
        NoAPIKeysError: Если ключи не найдены или некорректны

    Examples:
        >>> # Передача ключей списком
        >>> keys = parse_keys(api_keys=["key1", "key2", "key3"])

        >>> # Передача ключей строкой
        >>> keys = parse_keys(api_keys="key1,key2,key3")

        >>> # Загрузка из переменной окружения
        >>> os.environ["API_KEYS"] = "key1,key2"
        >>> keys = parse_keys()

        >>> # Загрузка из кастомной переменной
        >>> os.environ["MY_KEYS"] = "key1,key2"
        >>> keys = parse_keys(env_var="MY_KEYS")
    """
    logger = logger if logger else _setup_default_logger()

    # Случай 1: Ключи переданы напрямую
    if api_keys is not None:
        if isinstance(api_keys, str):
            # Парсинг строки с разделителями-запятыми
            keys = [k.strip() for k in api_keys.split(",") if k.strip()]
        elif isinstance(api_keys, list):
            # Очистка списка от пустых строк и пробелов
            keys = [k.strip() for k in api_keys if k and k.strip()]
        else:
            logger.error("❌ API keys must be a list or comma-separated string.")
            raise NoAPIKeysError("❌ API keys must be a list or comma-separated string")

        if not keys:
            logger.error("❌ No API keys provided in the api_keys parameter.")
            raise NoAPIKeysError("❌ No API keys provided in the api_keys parameter")

        logger.debug(f"✅ Parsed {len(keys)} keys from api_keys parameter")
        return keys

    # Случай 2: Загрузка из переменной окружения
    keys_str = os.getenv(env_var)

    if keys_str is None:
        error_msg = (
            f"❌ No API keys found.\n"
            f"   Please either:\n"
            f"   1. Pass keys directly: APIKeyRotator(api_keys=[\"key1\", \"key2\"])\n"
            f"   2. Set environment variable: export {env_var}='key1,key2'\n"
            f"   3. Create .env file with: {env_var}=key1,key2\n"
        )
        logger.error(error_msg)
        raise NoAPIKeysError(error_msg)

    if not keys_str.strip():
        error_msg = (
            f"❌ Environment variable ${env_var} is empty.\n"
            f"   Please set it with: export {env_var}='your_key1,your_key2'"
        )
        logger.error(error_msg)
        raise NoAPIKeysError(error_msg)

    # Парсинг ключей из переменной окружения
    keys = [k.strip() for k in keys_str.split(",") if k.strip()]

    if not keys:
        error_msg = (
            f"❌ No valid API keys found in ${env_var}.\n"
            f"   Format should be: key1,key2,key3\n"
            f"   Current value: '{keys_str}'"
        )
        logger.error(error_msg)
        raise NoAPIKeysError(error_msg)

    logger.debug(f"✅ Parsed {len(keys)} keys from environment variable ${env_var}")
    return keys


def validate_key_format(key: str, key_format: Optional[str] = None) -> bool:
    """
    Валидирует формат API ключа.

    Args:
        key: API ключ для валидации
        key_format: Ожидаемый формат ('openai', 'uuid', 'alphanumeric', etc.)
                   Если None, считается валидным любой непустой ключ

    Returns:
        bool: True если ключ валиден, False иначе

    Examples:
        >>> validate_key_format("sk-1234567890", "openai")
        True
        >>> validate_key_format("invalid", "openai")
        False
    """
    if not key or not key.strip():
        return False

    if key_format is None:
        return True

    key = key.strip()

    if key_format == "openai":
        # OpenAI ключи начинаются с "sk-" или "pk-"
        return key.startswith(("sk-", "pk-")) and len(key) > 10
    elif key_format == "uuid":
        # UUID формат (32 hex символа с дефисами)
        import re
        uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        return bool(re.match(uuid_pattern, key.lower()))
    elif key_format == "alphanumeric":
        # Только буквы и цифры
        return key.isalnum()
    elif key_format == "hex":
        # Только hex символы
        try:
            int(key, 16)
            return True
        except ValueError:
            return False

    return True


def filter_valid_keys(
        keys: List[str],
        key_format: Optional[str] = None,
        logger: Optional[logging.Logger] = None
) -> List[str]:
    """
    Фильтрует список ключей, оставляя только валидные.

    Args:
        keys: Список ключей для фильтрации
        key_format: Ожидаемый формат ключей
        logger: Логгер для вывода предупреждений

    Returns:
        List[str]: Список валидных ключей

    Examples:
        >>> keys = ["sk-valid1", "invalid", "sk-valid2"]
        >>> valid = filter_valid_keys(keys, key_format="openai")
        >>> print(valid)
        ['sk-valid1', 'sk-valid2']
    """
    logger = logger if logger else _setup_default_logger()
    valid_keys = []

    for key in keys:
        if validate_key_format(key, key_format):
            valid_keys.append(key)
        else:
            logger.warning(f"⚠️ Skipping invalid key: {key[:8]}...")

    return valid_keys