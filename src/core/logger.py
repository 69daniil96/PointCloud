"""
Модуль логирования для проекта.
Предоставляет централизованное логирование со сгруемотрой и выводом в файл.
"""

import logging
import logging.handlers
from pathlib import Path
from typing import Optional


class Logger:
    """Класс для инициализации и управления логированием."""
    
    _loggers = {}
    
    @classmethod
    def setup(
        cls,
        name: str,
        level: str = "INFO",
        log_file: Optional[str] = None,
        format_string: Optional[str] = None
    ) -> logging.Logger:
        """
        Настраивает и возвращает логгер.
        
        Args:
            name: Имя логгера (обычно __name__)
            level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            log_file: Путь к файлу логов (если None, логирование только в консоль)
            format_string: Кастомный формат логирования
            
        Returns:
            Настроенный логгер
        """
        if name in cls._loggers:
            return cls._loggers[name]
            
        # Стандартный формат
        if format_string is None:
            format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        
        formatter = logging.Formatter(format_string)

        # Настраиваем ROOT логгер — все дочерние логгеры ('cli', 'adapter.*' и др.)
        # автоматически наследуют хендлеры через propagate=True
        root = logging.getLogger()
        root.setLevel(getattr(logging, level.upper()))

        # Добавляем консольный хендлер только если его ещё нет
        if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
                   for h in root.handlers):
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            root.addHandler(console_handler)
        
        # Файловый обработчик (если указан)
        if log_file:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=10_000_000,  # 10MB
                backupCount=5
            )
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)

        # Именованный логгер без собственных хендлеров — использует root
        logger = logging.getLogger(name)
        logger.setLevel(getattr(logging, level.upper()))
        
        cls._loggers[name] = logger
        return logger
    
    @classmethod
    def get(cls, name: str) -> logging.Logger:
        """Получает логгер по имени."""
        return logging.getLogger(name)


def get_logger(name: str) -> logging.Logger:
    """Вспомогательная функция для получения логгера."""
    return Logger.get(name)
