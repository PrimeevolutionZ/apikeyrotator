"""Secret provider from file"""

import os
import json
from typing import List


class FileSecretProvider:
    """
    Secret provider from file.

    Supports formats:
    - JSON array: ["key1", "key2", "key3"]
    - CSV: key1,key2,key3
    - One key per line
    """

    def __init__(self, file_path: str):
        self.file_path = file_path

    async def get_keys(self) -> List[str]:
        if not os.path.exists(self.file_path):
            return []

        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Try parsing as JSON
            try:
                keys = json.loads(content)
                if isinstance(keys, list):
                    return [str(k).strip() for k in keys if k]
            except json.JSONDecodeError:
                pass

            # Parse as CSV or line-by-line
            if ',' in content:
                return [k.strip() for k in content.split(",") if k.strip()]
            else:
                return [k.strip() for k in content.split("\n") if k.strip()]
        except Exception as e:
            print(f"Error reading keys from {self.file_path}: {e}")
            return []

    async def refresh_keys(self) -> List[str]:
        return await self.get_keys()