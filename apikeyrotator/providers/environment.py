"""Secret provider from environment variables"""

import os
from typing import List


class EnvironmentSecretProvider:
    """
    Secret provider from environment variables.

    Loads API keys from an environment variable.
    Supports format: key1,key2,key3
    """

    def __init__(self, env_var: str = "API_KEYS"):
        self.env_var = env_var

    async def get_keys(self) -> List[str]:
        keys_str = os.getenv(self.env_var)
        if not keys_str:
            return []
        return [k.strip() for k in keys_str.split(",") if k.strip()]

    async def refresh_keys(self) -> List[str]:
        return await self.get_keys()