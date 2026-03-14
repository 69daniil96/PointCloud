"""
Базовый класс для pipelines - конвейеры обработки облаков точек.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
import json
import time

from src.core import get_logger


class BasePipeline(ABC):
    """Абстрактный класс для конвейеров обработки."""
    
    def __init__(self, name: str, output_dir: Path):
        """
        Инициализирует конвейер.
        
        Args:
            name: Имя конвейера
            output_dir: Папка для результатов
        """
        self.name = name
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger = get_logger(f"pipeline.{name.lower()}")
        
        # Статистика выполнения
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.stages: Dict[str, Dict[str, Any]] = {}  # История работы этапов
        self.success = False
    
    @abstractmethod
    def execute(self, *args, **kwargs) -> bool:
        """Выполняет конвейер обработки."""
        pass
    
    def log_stage(
        self,
        stage_name: str,
        success: bool,
        duration: float,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Логирует завершение этапа.
        
        Args:
            stage_name: Имя этапа
            success: Успешен ли этап
            duration: Длительность выполнения в секундах
            details: Дополнительные детали
        """
        self.stages[stage_name] = {
            'success': success,
            'duration': duration,
            'timestamp': datetime.now().isoformat(),
            'details': details or {},
        }
        
        status = "[OK]" if success else "[ERROR]"
        self.logger.info(f"{status} {stage_name} ({duration:.2f}s)")
    
    def get_execution_time(self) -> Optional[float]:
        """Получает общее время выполнения конвейера."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None
    
    def get_report(self) -> Dict[str, Any]:
        """Возвращает отчет о выполнении конвейера."""
        return {
            'pipeline': self.name,
            'success': self.success,
            'total_time': self.get_execution_time(),
            'start_time': datetime.fromtimestamp(self.start_time).isoformat() if self.start_time else None,
            'end_time': datetime.fromtimestamp(self.end_time).isoformat() if self.end_time else None,
            'stages': self.stages,
        }
    
    def save_report(self, report_file: Optional[Path] = None) -> Path:
        """
        Сохраняет отчет в JSON файл.
        
        Args:
            report_file: Путь к файлу отчета (если None, используется default)
            
        Returns:
            Путь к сохраненному файлу
        """
        if report_file is None:
            report_file = self.output_dir / f"{self.name}_report.json"
        
        report_file = Path(report_file)
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(self.get_report(), f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"Отчет сохранен: {report_file}")
        return report_file
