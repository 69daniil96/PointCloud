"""
Pipeline для обработки наземной съемки (COLMAP + PDAL + Open3D).
"""

import time
from pathlib import Path
from typing import Optional, Dict, Any, List

from .base_pipeline import BasePipeline
from src.adapters import ColmapRunner, PDALProcessor, Open3DProcessor, ContourGenerator
from src.core import get_config, get_path_manager


class GroundPipeline(BasePipeline):
    """Pipeline для обработки наземной съемки."""
    
    def __init__(self, output_dir: Optional[Path] = None):
        """
        Инициализирует pipeline для наземной съемки.
        
        Args:
            output_dir: Папка для результатов (если None, используется default)
        """
        if output_dir is None:
            path_manager = get_path_manager()
            output_dir = path_manager.get_output_dir() / "ground"
        
        super().__init__("GroundPipeline", output_dir)
        
        self.colmap = ColmapRunner()
        self.pdal = PDALProcessor()
        self.contours = ContourGenerator()
        self.open3d = Open3DProcessor()
    
    def execute(
        self,
        image_dir: Path,
        visualize: bool = True,
        visualize_layers: Optional[List[str]] = None,
        save_intermediate: bool = True,
        **kwargs
    ) -> bool:
        """
        Выполняет полный конвейер обработки наземной съемки.
        
        Этапы:
        1. COLMAP - 3D реконструкция из фотографий
        2. PDAL - пост-обработка облака точек
        3. Open3D - дополнительная обработка и визуализация
        
        Args:
            image_dir: Папка с изображениями
            visualize: Показать ли визуализацию облака в конце
            save_intermediate: Сохранять ли промежуточные файлы
            **kwargs: Дополнительные параметры
            
        Returns:
            True если конвейер выполнен успешно
        """
        self.start_time = time.time()
        image_dir = Path(image_dir)
        
        self.logger.info("=" * 60)
        self.logger.info(f"Запуск {self.name}")
        self.logger.info(f"Папка с изображениями: {image_dir}")
        self.logger.info("=" * 60)
        
        # Проверяем доступность инструментов
        if not self.colmap.is_available():
            self.logger.error("COLMAP недоступен")
            return False
        
        # Этап 1: COLMAP реконструкция
        self.logger.info("\n=== Этап 1: COLMAP Реконструкция ===")
        colmap_start = time.time()
        
        colmap_output_dir = self.output_dir / "colmap"
        colmap_output_dir.mkdir(parents=True, exist_ok=True)
        
        if not self.colmap.execute(image_dir, colmap_output_dir):
            self.logger.error("COLMAP реконструкция не удалась")
            self.success = False
            self.end_time = time.time()
            return False
        
        colmap_duration = time.time() - colmap_start
        self.log_stage("COLMAP Reconstruction", True, colmap_duration)
        
        # Ищем PLY файл из COLMAP
        colmap_ply = colmap_output_dir / "reconstruction.ply"
        if not colmap_ply.exists():
            # Ищем в других местах
            ply_files = list(colmap_output_dir.glob("**/*.ply"))
            if ply_files:
                colmap_ply = ply_files[0]
            else:
                self.logger.error("Не найден PLY файл из COLMAP")
                self.success = False
                self.end_time = time.time()
                return False
        
        self.logger.info(f"Облако из COLMAP: {colmap_ply}")
        
        # Этап 2: PDAL пост-обработка
        self.logger.info("\n=== Этап 2: PDAL Пост-обработка ===")
        
        if self.pdal.is_available():
            pdal_start = time.time()
            
            # Конвертируем PLY в LAS для PDAL (если нужно)
            # PDAL лучше работает с LAZ/LAS форматом
            pdal_output_dir = self.output_dir / "pdal"
            
            if self.pdal.execute(colmap_ply, pdal_output_dir):
                pdal_duration = time.time() - pdal_start
                self.log_stage("PDAL Post-processing", True, pdal_duration)
                pdal_layers = dict(self.pdal.last_outputs)
                
                # Ищем выходной файл PDAL
                las_files = list(pdal_output_dir.glob("*.las")) + list(pdal_output_dir.glob("*.laz"))
                if las_files:
                    current_cloud = las_files[-1]  # Берем последний обработанный файл
                    self.logger.info(f"Облако после PDAL: {current_cloud}")
                else:
                    current_cloud = colmap_ply
            else:
                self.logger.warning("PDAL пост-обработка пропущена")
                current_cloud = colmap_ply
                pdal_layers = {}
        else:
            self.logger.info("PDAL недоступен, пропуск пост-обработки")
            current_cloud = colmap_ply
            pdal_layers = {}
        
        # Этап 3: Построение изолиний
        self.logger.info("\n=== Этап 3: Построение изолиний ===")

        contours_file = None
        config = get_config()
        if config.get("contours.enabled", True):
            contour_start = time.time()
            contours_output_dir = self.output_dir / "contours"
            contours_output_dir.mkdir(parents=True, exist_ok=True)
            contours_file = contours_output_dir / f"{Path(current_cloud).stem}_contours.json"

            # По запросу: для ground используем псевдо-случайную геопривязку.
            if self.contours.generate_from_point_cloud(
                input_file=current_cloud,
                output_file=contours_file,
                apply_random_georef=True,
            ):
                contour_duration = time.time() - contour_start
                self.log_stage("Contour Generation", True, contour_duration)
            else:
                self.logger.warning("Построение изолиний пропущено")
                contours_file = None

        # Этап 4: Open3D обработка и сохранение
        self.logger.info("\n=== Этап 4: Open3D Обработка ===")
        
        if self.open3d.is_available():
            open3d_start = time.time()
            
            open3d_output_dir = self.output_dir / "open3d"
            
            if self.open3d.execute(current_cloud, open3d_output_dir):
                open3d_duration = time.time() - open3d_start
                self.log_stage("Open3D Processing", True, open3d_duration)
                
                final_ply = open3d_output_dir / f"{current_cloud.stem}_processed.ply"
                
                # Визуализация (если включена)
                if visualize and final_ply.exists():
                    self.logger.info("\nОтправка на визуализацию...")
                    layer_files = {
                        "final": final_ply,
                        "ground": pdal_layers.get("ground"),
                        "vegetation": pdal_layers.get("vegetation"),
                        "outliers": pdal_layers.get("outliers"),
                        "no_ground": pdal_layers.get("no_ground"),
                        "no_outliers": pdal_layers.get("no_outliers"),
                        "contours": contours_file,
                    }
                    self.open3d.visualize_layers(
                        layer_files=layer_files,
                        selected_layers=visualize_layers,
                        title="Ground Survey - Point Cloud Layers",
                    )
            else:
                self.logger.warning("Open3D обработка пропущена")
        else:
            self.logger.info("Open3D недоступен, пропуск обработки")
        
        # Завершение
        self.success = True
        self.end_time = time.time()
        
        self.logger.info("\n" + "=" * 60)
        self.logger.info(f"[OK] {self.name} завершен успешно")
        self.logger.info(f"Общее время: {self.get_execution_time():.2f} сек")
        self.logger.info("=" * 60)
        
        # Сохраняем отчет
        self.save_report()
        
        return True
