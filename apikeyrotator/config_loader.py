import os
import json
import yaml
from typing import Dict, Any, List, Optional

class ConfigLoader:
    def __init__(self, config_file: str):
        self.config_file = config_file
        self.config: Dict[str, Any] = {}

    def load_config(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_file):
            return {}

        _, ext = os.path.splitext(self.config_file)
        ext = ext.lower()

        with open(self.config_file, 'r') as f:
            if ext == '.json':
                self.config = json.load(f)
            elif ext in ('.yaml', '.yml'):
                self.config = yaml.safe_load(f)
            else:
                raise ValueError(f"Unsupported config file format: {ext}. Only .json, .yaml, .yml are supported.")
        return self.config

    def get(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    def save_config(self):
        _, ext = os.path.splitext(self.config_file)
        ext = ext.lower()

        with open(self.config_file, 'w') as f:
            if ext == '.json':
                json.dump(self.config, f, indent=4)
            elif ext in ('.yaml', '.yml'):
                yaml.safe_dump(self.config, f, indent=4)
            else:
                raise ValueError(f"Unsupported config file format: {ext}. Only .json, .yaml, .yml are supported.")

    def update_config(self, new_data: Dict[str, Any]):
        self.config.update(new_data)
        self.save_config()



