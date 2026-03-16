"""
Pipeline для обработки съемки с дронов (ODM + PDAL + Open3D).
"""

import time
from pathlib import Path
from typing import Optional, Dict, Any, List

from .base_pipeline import BasePipeline
from src.adapters import ODMRunner, PDALProcessor, Open3DProcessor, ContourGenerator
from src.core import get_config, get_path_manager


class DronePipeline(BasePipeline):
    """Pipeline для обработки съемки с дронов."""
    
    def __init__(self, output_dir: Optional[Path] = None):
        """
        Инициализирует pipeline для съемки с дронов.
        
        Args:
            output_dir: Папка для результатов (если None, используется default)
        """
        if output_dir is None:
            path_manager = get_path_manager()
            output_dir = path_manager.get_output_dir() / "drone"
        
        super().__init__("DronePipeline", output_dir)
        
        self.odm = ODMRunner()
        self.pdal = PDALProcessor()
        self.contours = ContourGenerator()
        self.open3d = Open3DProcessor()
    
    def execute(
        self,
        image_dir: Path,
        visualize: bool = True,
        visualize_layers: Optional[List[str]] = None,
        save_intermediate: bool = True,
        pull_docker_image: bool = False,
        **kwargs
    ) -> bool:
        """
        Выполняет полный конвейер обработки съемки с дронов.
        
        Этапы:
        1. ODM - обработка фотографий с дронов (SfM + MVS)
        2. PDAL - пост-обработка облака точек
        3. Open3D - дополнительная обработка и визуализация
        
        Args:
            image_dir: Папка с фотографиями с дронов
            visualize: Показать ли визуализацию облака в конце
            save_intermediate: Сохранять ли промежуточные файлы
            pull_docker_image: Загрузить ли Docker образ ODM (если его нет)
            **kwargs: Дополнительные параметры
            
        Returns:
            True если конвейер выполнен успешно
        """
        self.start_time = time.time()
        image_dir = Path(image_dir)
        
        self.logger.info("=" * 60)
        self.logger.info(f"Запуск {self.name}")
        self.logger.info(f"Папка с фотографиями дронов: {image_dir}")
        self.logger.info("=" * 60)
        
        # Проверяем доступность ODM
        if not self.odm.is_available():
            self.logger.error("ODM недоступен (Docker CLI или daemon недоступен)")
            
            if pull_docker_image:
                self.logger.info("Попытка загрузить Docker образ...")
                if self.odm.pull_image():
                    self.logger.info("Образ загружена. Пожалуйста, повторите команду.")
                else:
                    self.logger.error("Не удалось загрузить образ")
            
            self.success = False
            self.end_time = time.time()
            return False

        if not self.odm.is_image_available():
            if pull_docker_image:
                self.logger.info("ODM образ не найден. Загружаю образ перед запуском...")
                if not self.odm.pull_image():
                    self.logger.error("Не удалось загрузить ODM образ")
                    self.success = False
                    self.end_time = time.time()
                    return False
            else:
                self.logger.error(
                    "ODM образ не найден. Запустите с флагом --pull-docker-image "
                    "или выполните: docker pull opendronemap/odm:latest"
                )
                self.success = False
                self.end_time = time.time()
                return False
        
        # Этап 1: ODM обработка
        self.logger.info("\n=== Этап 1: ODM Обработка ===")
        odm_start = time.time()
        
        odm_output_dir = self.output_dir / "odm"
        odm_output_dir.mkdir(parents=True, exist_ok=True)
        
        if not self.odm.execute(image_dir, odm_output_dir):
            self.logger.error("ODM обработка не удалась")
            self.success = False
            self.end_time = time.time()
            return False
        
        odm_duration = time.time() - odm_start
        self.log_stage("ODM Processing", True, odm_duration)
        
        # Ищем облако из ODM (обычно в формате LAZ/LAS)
        point_cloud_files = (
            list(odm_output_dir.glob("**/*.laz")) +
            list(odm_output_dir.glob("**/*.las")) +
            list(odm_output_dir.glob("**/*.ply"))
        )
        
        if not point_cloud_files:
            self.logger.error("Не найдено облако точек из ODM")
            self.success = False
            self.end_time = time.time()
            return False
        
        # Берем скорей всего основное облако (обычно называется точка_cloud или opensfm_dense)
        odm_cloud = point_cloud_files[0]
        for f in point_cloud_files:
            if 'dense' in f.name.lower() or 'point_cloud' in f.name.lower():
                odm_cloud = f
                break
        
        self.logger.info(f"Облако из ODM: {odm_cloud}")
        
        # Этап 2: PDAL пост-обработка
        self.logger.info("\n=== Этап 2: PDAL Пост-обработка ===")
        
        if self.pdal.is_available():
            pdal_start = time.time()
            
            pdal_output_dir = self.output_dir / "pdal"
            
            if self.pdal.execute(odm_cloud, pdal_output_dir):
                pdal_duration = time.time() - pdal_start
                self.log_stage("PDAL Post-processing", True, pdal_duration)
                pdal_layers = dict(self.pdal.last_outputs)
                
                # Ищем выходной файл PDAL
                las_files = list(pdal_output_dir.glob("*.las")) + list(pdal_output_dir.glob("*.laz"))
                if las_files:
                    current_cloud = las_files[-1]  # Берем последний обработанный файл
                    self.logger.info(f"Облако после PDAL: {current_cloud}")
                else:
                    current_cloud = odm_cloud
            else:
                self.logger.warning("PDAL пост-обработка пропущена")
                current_cloud = odm_cloud
                pdal_layers = {}
        else:
            self.logger.info("PDAL недоступен, пропуск пост-обработки")
            current_cloud = odm_cloud
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

            if self.contours.generate_from_point_cloud(
                input_file=current_cloud,
                output_file=contours_file,
                apply_random_georef=False,
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
                        title="Drone Survey - Point Cloud Layers",
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
