import os
import json
import yaml
from typing import Dict, Any, List, Optional
import logging


class ConfigLoader:
    """
    Загрузчик конфигурации из файлов JSON/YAML.

    Поддерживает загрузку, сохранение и обновление конфигурации
    с автоматическим определением формата файла по расширению.

    Attributes:
        config_file (str): Путь к файлу конфигурации
        logger (Optional[logging.Logger]): Логгер для отладки
        config (Dict[str, Any]): Загруженная конфигурация
    """

    def __init__(self, config_file: str, logger: Optional[logging.Logger] = None):
        """
        Инициализирует загрузчик конфигурации.

        Args:
            config_file: Путь к файлу конфигурации (.json, .yaml, .yml)
            logger: Опциональный логгер для вывода сообщений
        """
        self.config_file = config_file
        self.logger = logger
        self.config: Dict[str, Any] = {}

    def load_config(self) -> Dict[str, Any]:
        """
        Загружает конфигурацию из файла.

        Автоматически определяет формат файла по расширению.
        Если файл не существует, возвращает пустой словарь.

        Returns:
            Dict[str, Any]: Загруженная конфигурация

        Raises:
            ValueError: Если формат файла не поддерживается
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
        Получает значение из конфигурации по ключу.

        Args:
            key: Ключ для поиска
            default: Значение по умолчанию, если ключ не найден

        Returns:
            Any: Значение из конфигурации или default
        """
        return self.config.get(key, default)

    def save_config(self, config: Optional[Dict[str, Any]] = None):
        """
        Сохраняет конфигурацию в файл.

        Args:
            config: Конфигурация для сохранения. Если None, сохраняет self.config

        Raises:
            ValueError: Если формат файла не поддерживается
        """
        if config is not None:
            self.config = config

        _, ext = os.path.splitext(self.config_file)
        ext = ext.lower()

        try:
            # Создаем директорию если не существует
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
        Обновляет конфигурацию новыми данными и сохраняет в файл.

        Args:
            new_data: Словарь с новыми данными для обновления
        """
        self.config.update(new_data)
        self.save_config()
        if self.logger:
            self.logger.debug(f"Updated config with new data")

    def clear(self):
        """Очищает текущую конфигурацию."""
        self.config = {}
        if self.logger:
            self.logger.debug("Cleared config")

    def delete_config_file(self):
        """Удаляет файл конфигурации."""
        if os.path.exists(self.config_file):
            os.remove(self.config_file)
            if self.logger:
                self.logger.debug(f"Deleted config file {self.config_file}")