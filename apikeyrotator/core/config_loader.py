import os
import json
import yaml
from typing import Dict, Any, List, Optional
import logging


class ConfigLoader:
    """
    Configuration loader from JSON/YAML files.

    Supports loading, saving and updating configuration
    with automatic file format detection by extension.

    Attributes:
        config_file (str): Path to the configuration file
        logger (Optional[logging.Logger]): Logger for debugging
        config (Dict[str, Any]): Loaded configuration
    """

    def __init__(self, config_file: str, logger: Optional[logging.Logger] = None):
        """
        Initializes the configuration loader.

        Args:
            config_file: Path to the configuration file (.json, .yaml, .yml)
            logger: Optional logger for output messages
        """
        self.config_file = config_file
        self.logger = logger
        self.config: Dict[str, Any] = {}

    def load_config(self) -> Dict[str, Any]:
        """
        Loads configuration from file.

        Automatically detects file format by extension.
        If the file does not exist, returns an empty dictionary.

        Returns:
            Dict[str, Any]: Loaded configuration

        Raises:
            ValueError: If the file format is not supported
        """
        if not os.path.exists(self.config_file):
            if self.logger:
                self.logger.debug(f"Config file {self.config_file} does not exist, returning empty config")
            return {}

        _, ext = os.path.splitext(self.config_file)
        ext = ext.lower()

        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                if ext == '.json':
                    self.config = json.load(f)
                elif ext in ('.yaml', '.yml'):
                    self.config = yaml.safe_load(f) or {}
                else:
                    raise ValueError(f"Unsupported config file format: {ext}. Only .json, .yaml, .yml are supported.")

            if self.logger:
                self.logger.debug(f"Loaded config from {self.config_file}")
            return self.config
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error loading config from {self.config_file}: {e}")
            return {}

    def get(self, key: str, default: Any = None) -> Any:
        """
        Gets a value from the configuration by key.

        Args:
            key: Key to search for
            default: Default value if the key is not found

        Returns:
            Any: Value from configuration or default
        """
        return self.config.get(key, default)

    def save_config(self, config: Optional[Dict[str, Any]] = None):
        """
        Saves the configuration to a file.

        Args:
            config: Configuration to save. If None, saves self.config

        Raises:
            ValueError: If the file format is not supported
        """
        if config is not None:
            self.config = config

        _, ext = os.path.splitext(self.config_file)
        ext = ext.lower()

        try:
            # Create directory if it does not exist
            os.makedirs(os.path.dirname(self.config_file) or '.', exist_ok=True)

            with open(self.config_file, 'w', encoding='utf-8') as f:
                if ext == '.json':
                    json.dump(self.config, f, indent=4, ensure_ascii=False)
                elif ext in ('.yaml', '.yml'):
                    yaml.safe_dump(self.config, f, indent=4, allow_unicode=True)
                else:
                    raise ValueError(f"Unsupported config file format: {ext}. Only .json, .yaml, .yml are supported.")

            if self.logger:
                self.logger.debug(f"Saved config to {self.config_file}")
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error saving config to {self.config_file}: {e}")
            raise

    def update_config(self, new_data: Dict[str, Any]):
        """
        Updates the configuration with new data and saves it to file.

        Args:
            new_data: Dictionary with new data to update
        """
        self.config.update(new_data)
        self.save_config()
        if self.logger:
            self.logger.debug(f"Updated config with new data")

    def clear(self):
        """Clears the current configuration."""
        self.config = {}
        if self.logger:
            self.logger.debug("Cleared config")

    def delete_config_file(self):
        """Deletes the configuration file."""
        if os.path.exists(self.config_file):
            os.remove(self.config_file)
            if self.logger:
                self.logger.debug(f"Deleted config file {self.config_file}")