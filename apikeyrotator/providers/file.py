"""Secret provider from file"""

import asyncio
import json
import logging
import os


class FileSecretProvider:
    """
    Secret provider from file.

    Supports formats:
    - JSON array: ["key1", "key2", "key3"]
    - CSV: key1,key2,key3
    - One key per line
    """

    def __init__(self, file_path: str, logger: logging.Logger | None = None):
        self.file_path = file_path
        self.logger = logger if logger else logging.getLogger(__name__)

    def _read_file(self) -> str:
        with open(self.file_path, encoding='utf-8') as f:
            return f.read()

    async def get_keys(self) -> list[str]:
        if not os.path.exists(self.file_path):
            self.logger.warning(f"Keys file {self.file_path} does not exist")
            return []

        try:
            # File I/O off the event loop
            loop = asyncio.get_running_loop()
            content = await loop.run_in_executor(None, self._read_file)

            # Try parsing as JSON
            try:
                keys = json.loads(content)
                if isinstance(keys, list):
                    return [str(k).strip() for k in keys if k is not None and str(k).strip()]
            except json.JSONDecodeError:
                pass

            # Parse as CSV and/or one key per line ('#' starts a comment line)
            keys = []
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                keys.extend(k.strip() for k in line.split(',') if k.strip())
            return keys
        except Exception as e:
            self.logger.error(f"Error reading keys from {self.file_path}: {e}")
            return []

    async def refresh_keys(self) -> list[str]:
        return await self.get_keys()