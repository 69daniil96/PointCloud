"""
Базовый класс для адаптеров (обертки над внешними инструментами).
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from pathlib import Path
import subprocess
import json
from datetime import datetime


class BaseAdapter(ABC):
    """Абстрактный класс для адаптеров инструментов."""
    
    def __init__(self, name: str):
        """
        Инициализирует адаптер.
        
        Args:
            name: Имя инструмента
        """
        self.name = name
        self.last_output: Optional[str] = None
        self.last_error: Optional[str] = None
        self.execution_time: Optional[float] = None
        
        # Импортируем логгер здесь, чтобы избежать циклических импортов
        from src.core import get_logger
        self.logger = get_logger(f"adapter.{name.lower()}")
    
    @abstractmethod
    def is_available(self) -> bool:
        """Проверяет, доступен ли инструмент в системе."""
        pass
    
    @abstractmethod
    def execute(self, *args, **kwargs) -> bool:
        """
        Выполняет основную операцию инструмента.
        
        Returns:
            True если успешно, False иначе
        """
        pass
    
    def run_command(
        self,
        command: List[str],
        capture_output: bool = True,
        check: bool = False
    ) -> subprocess.CompletedProcess:
        """
        Запускает команду в подпроцессе.
        
        Args:
            command: Список элементов команды
            capture_output: Захватывать ли вывод
            check: Вызывать ли исключение при ошибке
            
        Returns:
            CompletedProcess с результатами выполнения
        """
        import time
        
        self.logger.info(f"Выполнение: {' '.join(command)}")
        
        start_time = time.time()
        
        try:
            result = subprocess.run(
                command,
                capture_output=capture_output,
                text=True,
                check=False  # Обрабатываем ошибки сами
            )
            
            self.execution_time = time.time() - start_time
            self.last_output = result.stdout
            self.last_error = result.stderr
            
            if result.returncode != 0 and check:
                raise subprocess.CalledProcessError(
                    result.returncode,
                    command,
                    result.stdout,
                    result.stderr
                )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Ошибка выполнения: {e}")
            self.last_error = str(e)
            raise
    
    def log_success(self, message: str) -> None:
        """Логирует успешное выполнение."""
        self.logger.info(f"[OK] {message}")
    
    def log_error(self, message: str) -> None:
        """Логирует ошибку."""
        self.logger.error(f"[ERROR] {message}")
    
    def log_info(self, message: str) -> None:
        """Логирует информацию."""
        self.logger.info(message)
    
    def get_stats(self) -> Dict[str, Any]:
        """Возвращает статистику выполнения."""
        return {
            'tool': self.name,
            'execution_time': self.execution_time,
            'timestamp': datetime.now().isoformat(),
            'has_error': self.last_error is not None,
        }
