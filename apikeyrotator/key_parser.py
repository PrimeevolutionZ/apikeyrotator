import os
from typing import List, Optional, Union
import logging
from .exceptions import NoAPIKeysError

def _setup_default_logger():
    logger = logging.getLogger(__name__)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger

def parse_keys(api_keys: Optional[Union[List[str], str]] = None, env_var: str = "API_KEYS", logger: Optional[logging.Logger] = None) -> List[str]:
    """Умный парсинг ключей из разных источников с понятными ошибками"""
    logger = logger if logger else _setup_default_logger()

    if api_keys is not None:
        if isinstance(api_keys, str):
            keys = [k.strip() for k in api_keys.split(",") if k.strip()]
        elif isinstance(api_keys, list):
            keys = api_keys
        else:
            logger.error("❌ API keys must be a list or comma-separated string.")
            raise NoAPIKeysError("❌ API keys must be a list or comma-separated string")

        if not keys:
            logger.error("❌ No API keys provided in the api_keys parameter.")
            raise NoAPIKeysError("❌ No API keys provided in the api_keys parameter")

        return keys

    keys_str = os.getenv(env_var)

    if keys_str is None:
        error_msg = (
            f"❌ No API keys found.\n"
            f"   Please either:\n"
            f"   1. Pass keys directly: APIKeyRotator(api_keys=[\"key1\", \"key2\"])\n"
            f"   2. Set environment variable: export {env_var}=\'key1,key2\'\n"
            f"   3. Create .env file with: {env_var}=key1,2\n"
        )
        logger.error(error_msg)
        raise NoAPIKeysError(error_msg)

    if not keys_str.strip():
        error_msg = (
            f"❌ Environment variable ${env_var} is empty.\n"
            f"   Please set it with: export {env_var}=\'your_key1,your_key2\'"
        )
        logger.error(error_msg)
        raise NoAPIKeysError(error_msg)

    keys = [k.strip() for k in keys_str.split(",") if k.strip()]

    if not keys:
        error_msg = (
            f"❌ No valid API keys found in ${env_var}.\n"
            f"   Format should be: key1,key2,key3\n"
            f"   Current value: \'{keys_str}\'"
        )
        logger.error(error_msg)
        raise NoAPIKeysError(error_msg)

    return keys


