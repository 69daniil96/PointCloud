"""
Модуль для управления конфигурацией проекта.
Читает и парсит config.yaml, позволяет обращаться к параметрам как к атрибутам.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional, Union
import yaml
from dotenv import load_dotenv


class Config:
    """Класс для управления конфигурацией проекта."""
    
    _instance: Optional['Config'] = None
    _config: Dict[str, Any] = {}
    
    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Инициализирует конфигурацию (только при первом создании экземпляра)."""
        if not self._config:
            self.load()
    
    @classmethod
    def load(cls, config_path: Optional[Union[str, Path]] = None) -> None:
        """
        Загружает конфигурацию из YAML файла и переменных окружения.
        
        Args:
            config_path: Путь к config.yaml (если None, ищет в корне проекта)
        """
        # Загружаем переменные окружения из .env
        load_dotenv()

        # На Windows unix-сокет ломает Docker Desktop CLI.
        # Если такое значение пришло из .env, удаляем его.
        docker_host = os.getenv("DOCKER_HOST", "")
        if os.name == "nt" and docker_host.startswith("unix://"):
            os.environ.pop("DOCKER_HOST", None)
        
        # Определяем путь к config.yaml
        if config_path is None:
            # Ищем config.yaml в корне проекта
            project_root = Path(__file__).parent.parent.parent
            config_file = project_root / "config.yaml"
        else:
            config_file = Path(config_path)
        
        # Загружаем YAML конфиг
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                cls._config = yaml.safe_load(f) or {}
        else:
            raise FileNotFoundError(f"Конфиг-файл не найден: {config_file}")
    
    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        """
        Получает значение конфигурации по ключу с поддержкой вложенности.
        Использует точку как разделитель для вложенных ключей.
        
        Example:
            Config.get("colmap.feature_extraction.camera_model")
            Config.get("colmap.feature_extraction.camera_model", "PINHOLE")
        
        Args:
            key: Ключ конфигурации (вложенность через точку)
            default: Значение по умолчанию, если ключ не найден
            
        Returns:
            Значение конфигурации или default
        """
        keys = key.split('.')
        value = cls._config
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        
        return value
    
    @classmethod
    def get_or_env(cls, key: str, env_var: str, default: Any = None) -> Any:
        """
        Получает значение из конфига, затем проверяет переменную окружения.
        
        Args:
            key: Ключ конфигурации
            env_var: Имя переменной окружения
            default: Значение по умолчанию
            
        Returns:
            Значение из конфига, переменной окружения или default
        """
        config_value = cls.get(key)
        if config_value is not None:
            return config_value
        
        env_value = os.getenv(env_var)
        if env_value is not None:
            return env_value
        
        return default
    
    @classmethod
    def to_dict(cls) -> Dict[str, Any]:
        """Возвращает весь конфиг как словарь."""
        return cls._config.copy()
    
    def __getattr__(self, name: str) -> Any:
        """Позволяет обращаться к конфигу как к атрибутам (Config().colmap)."""
        return self._config.get(name)


# Глобальный экземпляр конфига
_config = Config()


def get_config() -> Config:
    """Возвращает глобальный экземпляр конфигурации."""
    return _config
