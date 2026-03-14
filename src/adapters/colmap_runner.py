"""
Адаптер для COLMAP - инструмента 3D реконструкции для наземной съемки.
"""

import os
import sys
import shutil
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any
import json

from .base_adapter import BaseAdapter
from src.core import get_config, get_logger


class ColmapRunner(BaseAdapter):
    """Адаптер для запуска COLMAP через subprocess."""
    
    def __init__(self):
        """Инициализирует COLMAP адаптер."""
        super().__init__("COLMAP")
        self.colmap_exe = self._find_colmap_executable()
        self.database_path: Optional[Path] = None
        self.image_path: Optional[Path] = None
        self.output_path: Optional[Path] = None
    
    def _find_colmap_executable(self) -> Optional[str]:
        """Ищет COLMAP исполняемый файл в системе."""
        config = get_config()
        
        # Сначала проверяем config
        colmap_exe = config.get("colmap.executable")
        if colmap_exe and self._check_executable(colmap_exe):
            return colmap_exe
        
        # Для Windows проверяем в Conda окружении
        if sys.platform == "win32":
            base_path = sys.base_prefix
            colmap_path = os.path.join(base_path, 'Library', 'bin', 'colmap.exe')
            if self._check_executable(colmap_path):
                return colmap_path
        
        # Проверяем PATH
        colmap_exe = shutil.which("colmap.exe") if sys.platform == "win32" else shutil.which("colmap")
        if colmap_exe:
            return colmap_exe
        
        return None
    
    def _check_executable(self, exe_path: str) -> bool:
        """Проверяет, существует ли и исполняемый ли файл."""
        return os.path.isfile(exe_path) and os.access(exe_path, os.X_OK)
    
    def is_available(self) -> bool:
        """Проверяет, доступен ли COLMAP."""
        available = self.colmap_exe is not None
        if available:
            self.log_success(f"COLMAP найден: {self.colmap_exe}")
        else:
            self.log_error("COLMAP не найден в системе")
        return available
    
    def extract_features(
        self,
        image_dir: Path,
        database_path: Path,
        **kwargs
    ) -> bool:
        """
        Извлекает признаки (features) из изображений.
        
        Args:
            image_dir: Папка с изображениями
            database_path: Путь к БД COLMAP
            **kwargs: Дополнительные параметры
            
        Returns:
            True если успешно
        """
        if not self.is_available():
            return False
        
        image_dir = Path(image_dir)
        database_path = Path(database_path)
        
        config = get_config()
        camera_model = config.get("colmap.feature_extraction.camera_model", "SIMPLE_RADIAL")
        single_camera = config.get("colmap.feature_extraction.single_camera", False)
        
        command = [
            self.colmap_exe,
            "feature_extractor",
            "--database_path", str(database_path),
            "--image_path", str(image_dir),
            "--ImageReader.camera_model", camera_model,
        ]
        
        if single_camera:
            command.append("--ImageReader.single_camera_per_folder=1")
        
        self.log_info(f"Извлечение признаков из {len(list(image_dir.glob('*.*')))} изображений...")
        
        try:
            result = self.run_command(command, check=True)
            self.log_success("Признаки извлечены успешно")
            return result.returncode == 0
        except Exception as e:
            self.log_error(f"Ошибка при извлечении признаков: {e}")
            return False
    
    def match_features(
        self,
        database_path: Path,
        **kwargs
    ) -> bool:
        """
        Сопоставляет признаки между изображениями.
        
        Args:
            database_path: Путь к БД COLMAP
            **kwargs: Дополнительные параметры
            
        Returns:
            True если успешно
        """
        if not self.is_available():
            return False
        
        database_path = Path(database_path)
        config = get_config()
        guided_matching = config.get("colmap.matching.guided_matching", True)
        
        command = [
            self.colmap_exe,
            "exhaustive_matcher",
            "--database_path", str(database_path),
        ]
        
        self.log_info("Сопоставление признаков между изображениями...")
        
        try:
            result = self.run_command(command, check=True)
            
            # Опциональное направленное сопоставление
            if guided_matching:
                self.log_info("Направленное сопоставление...")
                guided_command = [
                    self.colmap_exe,
                    "spatial_matcher",
                    "--database_path", str(database_path),
                ]
                self.run_command(guided_command, check=True)
            
            self.log_success("Признаки сопоставлены успешно")
            return result.returncode == 0
        except Exception as e:
            self.log_error(f"Ошибка при сопоставлении: {e}")
            return False
    
    def reconstruct(
        self,
        database_path: Path,
        image_dir: Path,
        output_dir: Path,
        **kwargs
    ) -> bool:
        """
        Выполняет 3D реконструкцию.
        
        Args:
            database_path: Путь к БД COLMAP
            image_dir: Папка с изображениями
            output_dir: Папка для сохранения результатов
            **kwargs: Дополнительные параметры
            
        Returns:
            True если успешно
        """
        if not self.is_available():
            return False
        
        database_path = Path(database_path)
        image_dir = Path(image_dir)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        config = get_config()
        num_threads = config.get("colmap.reconstruction.num_threads", 4)
        
        command = [
            self.colmap_exe,
            "mapper",
            "--database_path", str(database_path),
            "--image_path", str(image_dir),
            "--output_path", str(output_dir),
            "--Mapper.num_threads", str(num_threads),
        ]
        
        self.log_info("Выполнение 3D реконструкции (это может занять некоторое время)...")
        
        try:
            result = self.run_command(command, check=True)
            self.log_success("3D реконструкция завершена успешно")
            return result.returncode == 0
        except Exception as e:
            self.log_error(f"Ошибка при реконструкции: {e}")
            return False
    
    def export_model(
        self,
        sparse_dir: Path,
        output_ply: Path,
        **kwargs
    ) -> bool:
        """
        Экспортирует разреженное облако точек в PLY.
        
        Args:
            sparse_dir: Папка со разреженной реконструкцией
            output_ply: Путь для сохранения PLY
            **kwargs: Дополнительные параметры
            
        Returns:
            True если успешно
        """
        if not self.is_available():
            return False
        
        sparse_dir = Path(sparse_dir)
        output_ply = Path(output_ply)
        
        # Ищем папку 0 внутри sparse_dir (COLMAP создает её)
        actual_sparse_dir = sparse_dir / "0"
        if not actual_sparse_dir.exists():
            self.log_error(f"Разреженная реконструкция не найдена: {actual_sparse_dir}")
            return False
        
        command = [
            self.colmap_exe,
            "model_converter",
            "--input_path", str(actual_sparse_dir),
            "--output_path", str(output_ply),
            "--output_type", "PLY",
        ]
        
        self.log_info(f"Экспортирование облака точек в {output_ply}...")
        
        try:
            result = self.run_command(command, check=True)
            self.log_success("Облако точек экспортировано успешно")
            return result.returncode == 0
        except Exception as e:
            self.log_error(f"Ошибка при экспорте: {e}")
            return False
    
    def execute(self, image_dir: Path, output_dir: Path, **kwargs) -> bool:
        """
        Полный конвейер COLMAP: извлечение -> сопоставление -> реконструкция.
        
        Args:
            image_dir: Папка с изображениями
            output_dir: Папка для сохранения результатов
            **kwargs: Дополнительные параметры
            
        Returns:
            True если успешно
        """
        image_dir = Path(image_dir)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        self.log_info(f"Запуск полного конвейера COLMAP для {image_dir}")
        
        # Создаем временную БД
        database_path = output_dir / "database.db"
        
        # Если БД существует, удаляем её
        if database_path.exists():
            database_path.unlink()
        
        # Этап 1: Извлечение признаков
        if not self.extract_features(image_dir, database_path):
            return False
        
        # Этап 2: Сопоставление
        if not self.match_features(database_path):
            return False
        
        # Этап 3: Реконструкция
        sparse_dir = output_dir / "sparse"
        if not self.reconstruct(database_path, image_dir, sparse_dir):
            return False
        
        # Этап 4: Экспорт в PLY
        output_ply = output_dir / "reconstruction.ply"
        if not self.export_model(sparse_dir, output_ply):
            return False
        
        self.log_success(f"Конвейер COLMAP завершен успешно. Результат: {output_ply}")
        return True
