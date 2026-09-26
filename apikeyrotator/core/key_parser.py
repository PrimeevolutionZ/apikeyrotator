import logging
import os

from .exceptions import NoAPIKeysError


def _setup_default_logger() -> logging.Logger:
    """Library logger - output is configured by the application (see logging docs)."""
    return logging.getLogger(__name__)


def _dedupe(keys: list[str], logger: logging.Logger) -> list[str]:
    """Removes duplicate keys while preserving order."""
    unique = list(dict.fromkeys(keys))
    if len(unique) != len(keys):
        logger.warning(f"Removed {len(keys) - len(unique)} duplicate API key(s)")
    return unique


def parse_keys(
        api_keys: list[str] | str | None = None,
        env_var: str = "API_KEYS",
        logger: logging.Logger | None = None
) -> list[str]:
    """
    Smart parser for API keys from various sources.

    Supports loading keys:
    1. Directly via api_keys parameter (list or comma-separated string)
    2. From environment variable
    3. From .env file (if python-dotenv is used)

    Args:
        api_keys: Keys as a list or comma-separated string.
                 If None, tries to load from environment variable.
        env_var: Environment variable name for loading keys.
                Default is "API_KEYS".
        logger: Logger for output messages. If None, a new one is created.

    Returns:
        List[str]: List of valid API keys (no empty strings or spaces)

    Raises:
        NoAPIKeysError: If keys are not found or invalid

    Examples:
        >>> # Passing keys as list
        >>> keys = parse_keys(api_keys=["key1", "key2", "key3"])

        >>> # Passing keys as string
        >>> keys = parse_keys(api_keys="key1,key2,key3")

        >>> # Loading from environment variable
        >>> os.environ["API_KEYS"] = "key1,key2"
        >>> keys = parse_keys()

        >>> # Loading from custom variable
        >>> os.environ["MY_KEYS"] = "key1,key2"
        >>> keys = parse_keys(env_var="MY_KEYS")
    """
    logger = logger if logger else _setup_default_logger()

    # Case 1: Keys passed directly
    if api_keys is not None:
        given: object = api_keys   # callers without type checking may pass anything
        if isinstance(given, str):
            # Parsing comma-separated string
            keys = [k.strip() for k in given.split(",") if k.strip()]
        elif isinstance(given, (list, tuple)):
            # Cleaning list from empty strings and spaces
            keys = [k.strip() for k in given if isinstance(k, str) and k.strip()]
        else:
            logger.error("API keys must be a list or comma-separated string.")
            raise NoAPIKeysError("API keys must be a list or comma-separated string")

        if not keys:
            logger.error("No API keys provided in the api_keys parameter.")
            raise NoAPIKeysError("No API keys provided in the api_keys parameter")

        keys = _dedupe(keys, logger)
        logger.debug(f"Parsed {len(keys)} keys from api_keys parameter")
        return keys

    # Case 2: Loading from environment variable
    keys_str = os.getenv(env_var)

    if keys_str is None:
        error_msg = (
            f"No API keys found.\n"
            f"   Please either:\n"
            f"   1. Pass keys directly: APIKeyRotator(api_keys=[\"key1\", \"key2\"])\n"
            f"   2. Set environment variable: export {env_var}='key1,key2'\n"
            f"   3. Put {env_var}=key1,key2 in a .env file and pass load_env_file=True\n"
        )
        if os.path.exists(".env"):
            error_msg += "   (a .env file exists in the current directory - pass load_env_file=True to read it)\n"
        logger.error(error_msg)
        raise NoAPIKeysError(error_msg)

    if not keys_str.strip():
        error_msg = (
            f"Environment variable ${env_var} is empty.\n"
            f"   Please set it with: export {env_var}='your_key1,your_key2'"
        )
        logger.error(error_msg)
        raise NoAPIKeysError(error_msg)

    # Parsing keys from environment variable
    keys = [k.strip() for k in keys_str.split(",") if k.strip()]

    if not keys:
        error_msg = (
            f"No valid API keys found in ${env_var}.\n"
            f"   Format should be: key1,key2,key3"
        )
        logger.error(error_msg)
        raise NoAPIKeysError(error_msg)

    keys = _dedupe(keys, logger)
    logger.debug(f"Parsed {len(keys)} keys from environment variable ${env_var}")
    return keys


def validate_key_format(key: str, key_format: str | None = None) -> bool:
    """
    Validates the format of an API key.

    Args:
        key: API key to validate
        key_format: Expected format ('openai', 'uuid', 'alphanumeric', etc.)
                   If None, any non-empty key is considered valid

    Returns:
        bool: True if key is valid, False otherwise

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
        # OpenAI keys start with "sk-" or "pk-"
        return key.startswith(("sk-", "pk-")) and len(key) > 10
    elif key_format == "uuid":
        # UUID format (32 hex characters with dashes)
        import re
        uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        return bool(re.match(uuid_pattern, key.lower()))
    elif key_format == "alphanumeric":
        # Only letters and digits
        return key.isalnum()
    elif key_format == "hex":
        # Only hex characters
        try:
            int(key, 16)
            return True
        except ValueError:
            return False

    return True


def filter_valid_keys(
        keys: list[str],
        key_format: str | None = None,
        logger: logging.Logger | None = None
) -> list[str]:
    """
    Filters a list of keys, keeping only valid ones.

    Args:
        keys: List of keys to filter
        key_format: Expected key format
        logger: Logger for warning messages

    Returns:
        List[str]: List of valid keys

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
            logger.warning(f"Skipping invalid key: {key[:8]}...")

    return valid_keys