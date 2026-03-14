"""
Адаптер для PDAL - фильтрации и обработки облаков точек.
"""

import json
from pathlib import Path
from typing import Optional, List, Dict, Any

from .base_adapter import BaseAdapter
from src.core import get_config, get_logger


class PDALProcessor(BaseAdapter):
    """Адаптер для работы с PDAL через Python API."""
    
    def __init__(self):
        """Инициализирует PDAL адаптер."""
        super().__init__("PDAL")
        self.pdal = None
        self.last_outputs: Dict[str, Path] = {}
        self._initialize_pdal()

    def _split_by_expression(
        self,
        input_file: Path,
        output_file: Path,
        expression: str,
    ) -> bool:
        """Фильтрует облако по PDAL expression и сохраняет результат."""
        input_file = Path(input_file)
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            reader = self.pdal.Reader(str(input_file))
            pipeline = reader | self.pdal.Filter.expression(expression=expression)
            writer = pipeline | self.pdal.Writer(str(output_file), forward="all")
            writer.execute()
            return True
        except Exception as e:
            self.log_error(
                f"Ошибка фильтрации expression '{expression}' для {input_file}: {e}"
            )
            return False
    
    def _initialize_pdal(self) -> None:
        """Инициализирует PDAL модуль."""
        try:
            import pdal
            self.pdal = pdal
            self.log_success(f"PDAL инициализирован (версия {pdal.__version__})")
        except ImportError as e:
            self.log_error(f"PDAL не установлен: {e}")
    
    def is_available(self) -> bool:
        """Проверяет, доступен ли PDAL."""
        available = self.pdal is not None
        if not available:
            self.log_error("PDAL не доступен (не установлен)")
        return available
    
    def remove_outliers(
        self,
        input_file: Path,
        output_file: Path,
        outliers_output_file: Optional[Path] = None,
        **kwargs
    ) -> bool:
        """
        Удаляет выбросы из облака точек.
        
        Args:
            input_file: Входной файл облака точек (.laz, .las, .ply)
            output_file: Выходной файл без выбросов
            outliers_output_file: Файл со слоем выбросов (если указан)
            **kwargs: Дополнительные параметры
            
        Returns:
            True если успешно
        """
        if not self.is_available():
            return False
        
        input_file = Path(input_file)
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        config = get_config()
        method = config.get("pdal.filters.outlier_removal.method", "statistical")
        
        self.log_info(f"Удаление выбросов из {input_file} методом '{method}'...")
        
        try:
            if method == "statistical":
                # Статистический метод (используется mean_k и std_dev)
                mean_k = config.get("pdal.filters.outlier_removal.params.mean_k", 8)
                std_dev = config.get("pdal.filters.outlier_removal.params.std_dev_threshold", 2.0)

                # Сначала помечаем выбросы как Classification=7.
                classified_file = output_file.parent / f"{input_file.stem}_outlier_classified.las"

                reader = self.pdal.Reader(str(input_file))
                pipeline = reader | self.pdal.Filter.outlier(
                    method="statistical",
                    mean_k=mean_k,
                    multiplier=std_dev
                )
                writer = pipeline | self.pdal.Writer(str(classified_file), forward="all")
                writer.execute()

                # Слой без выбросов.
                if not self._split_by_expression(
                    classified_file,
                    output_file,
                    "Classification != 7"
                ):
                    return False

                # Отдельный слой выбросов (опционально).
                if outliers_output_file is not None:
                    if not self._split_by_expression(
                        classified_file,
                        outliers_output_file,
                        "Classification == 7"
                    ):
                        self.log_warning("Не удалось сохранить отдельный слой выбросов")
                
            else:
                # Простой пассквой (копируем без фильтрации)
                self.log_warning(f"Неподдерживаемый метод: {method}. Скопирую файл.")
                import shutil
                shutil.copy2(input_file, output_file)
            
            self.log_success(f"Выбросы удалены. Результат: {output_file}")
            return True
            
        except Exception as e:
            self.log_error(f"Ошибка при удалении выбросов: {e}")
            return False

    def classify_ground_and_extract_layers(
        self,
        input_file: Path,
        ground_output: Path,
        non_ground_output: Path,
        vegetation_output: Optional[Path] = None,
    ) -> bool:
        """
        Классифицирует землю (SMRF) и извлекает слои земли/не-земли/растительности.
        """
        if not self.is_available():
            return False

        input_file = Path(input_file)
        ground_output = Path(ground_output)
        non_ground_output = Path(non_ground_output)
        if vegetation_output is not None:
            vegetation_output = Path(vegetation_output)

        ground_output.parent.mkdir(parents=True, exist_ok=True)
        non_ground_output.parent.mkdir(parents=True, exist_ok=True)
        if vegetation_output is not None:
            vegetation_output.parent.mkdir(parents=True, exist_ok=True)

        config = get_config()

        smrf_config = config.get("pdal.filters.ground_classification", {}) or {}
        slope = smrf_config.get("slope", 0.2)
        window = smrf_config.get("window", 16.0)
        threshold = smrf_config.get("threshold", 0.45)
        scalar = smrf_config.get("scalar", 1.25)

        classified_file = ground_output.parent / f"{input_file.stem}_ground_classified.las"

        self.log_info(
            "Классификация земли (SMRF): "
            f"slope={slope}, window={window}, threshold={threshold}, scalar={scalar}"
        )

        try:
            reader = self.pdal.Reader(str(input_file))
            pipeline = reader | self.pdal.Filter.smrf(
                slope=slope,
                window=window,
                threshold=threshold,
                scalar=scalar,
            )
            writer = pipeline | self.pdal.Writer(str(classified_file), forward="all")
            writer.execute()

            if not self._split_by_expression(classified_file, ground_output, "Classification == 2"):
                return False

            if not self._split_by_expression(classified_file, non_ground_output, "Classification != 2"):
                return False

            # ASPRS: 3/4/5 - low/medium/high vegetation.
            if vegetation_output is not None:
                if not self._split_by_expression(
                    classified_file,
                    vegetation_output,
                    "Classification == 3 || Classification == 4 || Classification == 5"
                ):
                    self.log_warning("Не удалось извлечь слой растительности")

            self.log_success("Классификация земли и извлечение слоев завершены")
            return True

        except Exception as e:
            self.log_error(f"Ошибка классификации земли: {e}")
            return False
    
    def remove_ground(
        self,
        input_file: Path,
        output_file: Path,
        height_threshold: float = 0.5,
        **kwargs
    ) -> bool:
        """
        Удаляет точки ниже определенной высоты (например, земля).
        
        Args:
            input_file: Входной файл
            output_file: Выходной файл
            height_threshold: Порог высоты (в метрах)
            **kwargs: Дополнительные параметры
            
        Returns:
            True если успешно
        """
        if not self.is_available():
            return False
        
        input_file = Path(input_file)
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        config = get_config()
        if height_threshold is None:
            height_threshold = config.get("pdal.filters.ground_removal.height_threshold", 0.5)
        
        self.log_info(f"Удаление точек ниже {height_threshold}м...")
        
        try:
            # Создаем фильтр для удаления низких точек
            reader = self.pdal.Reader(str(input_file))
            # Фильтруем по Z координате
            pipeline = reader | self.pdal.Filter.expression(
                expression=f"Z > {height_threshold}"
            )
            writer = pipeline | self.pdal.Writer(str(output_file), forward="all")
            
            writer.execute()
            
            self.log_success(f"Низкие точки удалены. Результат: {output_file}")
            return True
            
        except Exception as e:
            self.log_error(f"Ошибка при удалении земли: {e}")
            return False
    
    def downsample(
        self,
        input_file: Path,
        output_file: Path,
        voxel_size: Optional[float] = None,
        **kwargs
    ) -> bool:
        """
        Уменьшает плотность облака точек (вокселизация).
        
        Args:
            input_file: Входной файл
            output_file: Выходной файл
            voxel_size: Размер вокселя (в метрах)
            **kwargs: Дополнительные параметры
            
        Returns:
            True если успешно
        """
        if not self.is_available():
            return False
        
        input_file = Path(input_file)
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        config = get_config()
        if voxel_size is None:
            voxel_size = config.get("pdal.filters.voxel_downsampling.voxel_size", 0.05)
        
        self.log_info(f"Даунсемплинг облака точек (размер вокселя: {voxel_size}м)...")
        
        try:
            reader = self.pdal.Reader(str(input_file))
            # PDAL фильтр для вокселизации
            pipeline = reader | self.pdal.Filter.voxelcentroidnearestneighbor(
                cell=voxel_size
            )
            writer = pipeline | self.pdal.Writer(str(output_file), forward="all")
            
            writer.execute()
            
            self.log_success(f"Даунсемплинг завершен. Результат: {output_file}")
            return True
            
        except Exception as e:
            self.log_error(f"Ошибка при даунсемплинге: {e}")
            return False
    
    def get_info(self, file_path: Path) -> Dict[str, Any]:
        """
        Получает информацию об облаке точек.
        
        Args:
            file_path: Путь к файлу облака точек
            
        Returns:
            Словарь с информацией о облаке
        """
        if not self.is_available():
            return {}
        
        file_path = Path(file_path)
        
        try:
            reader = self.pdal.Reader(str(file_path))
            reader.execute()
            
            # Получаем информацию из метаданных
            metadata = json.loads(reader.metadata)
            
            return {
                'point_count': metadata.get('count', 0),
                'bounds': metadata.get('readers.0.bounds'),
                'schema': metadata.get('readers.0.schema'),
            }
            
        except Exception as e:
            self.log_error(f"Ошибка при чтении информации: {e}")
            return {}
    
    def log_warning(self, message: str) -> None:
        """Логирует предупреждение."""
        self.logger.warning(message)
    
    def execute(
        self,
        input_file: Path,
        output_dir: Path,
        pipeline_config: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> bool:
        """
        Выполняет полный конвейер обработки облака точек.
        
        Args:
            input_file: Входной файл облака точек
            output_dir: Папка для сохранения результатов
            pipeline_config: Конфигурация конвейера
            **kwargs: Дополнительные параметры
            
        Returns:
            True если успешно
        """
        if not self.is_available():
            return False
        
        input_file = Path(input_file)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        config = get_config()
        current_file = input_file
        self.last_outputs = {
            "input": input_file,
        }
        
        # Этап 1: Удаление выбросов
        remove_outliers = config.get("pdal.filters.outlier_removal.method") is not None
        if remove_outliers:
            outliers_output = output_dir / f"{input_file.stem}_no_outliers.las"
            outliers_layer_output = output_dir / f"{input_file.stem}_outliers.las"
            self.log_info("Этап 1: Удаление выбросов...")
            if not self.remove_outliers(
                current_file,
                outliers_output,
                outliers_output_file=outliers_layer_output,
            ):
                self.log_warning("Пропуск удаления выбросов")
            else:
                current_file = outliers_output
                self.last_outputs["no_outliers"] = outliers_output
                self.last_outputs["outliers"] = outliers_layer_output
        
        # Этап 2: Удаление земли
        remove_ground = config.get("pdal.filters.ground_removal.enabled", True)
        if remove_ground:
            ground_output = output_dir / f"{current_file.stem}_no_ground.las"
            ground_layer_output = output_dir / f"{current_file.stem}_ground.las"
            vegetation_layer_output = output_dir / f"{current_file.stem}_vegetation.las"
            self.log_info("Этап 2: Удаление земли...")

            use_smrf = config.get("pdal.filters.ground_removal.use_smrf_classification", True)
            if use_smrf:
                success = self.classify_ground_and_extract_layers(
                    current_file,
                    ground_output=ground_layer_output,
                    non_ground_output=ground_output,
                    vegetation_output=vegetation_layer_output,
                )
            else:
                height_threshold = config.get("pdal.filters.ground_removal.height_threshold", 0.5)
                success = self.remove_ground(current_file, ground_output, height_threshold)

            if not success:
                self.log_warning("Пропуск удаления земли")
            else:
                current_file = ground_output
                self.last_outputs["no_ground"] = ground_output
                if use_smrf:
                    self.last_outputs["ground"] = ground_layer_output
                    self.last_outputs["vegetation"] = vegetation_layer_output
        
        # Этап 3: Даунсемплинг
        downsample = config.get("pdal.filters.voxel_downsampling.enabled", True)
        if downsample:
            downsample_output = output_dir / f"{current_file.stem}_downsampled.las"
            self.log_info("Этап 3: Даунсемплинг...")
            voxel_size = config.get("pdal.filters.voxel_downsampling.voxel_size", 0.05)
            if not self.downsample(current_file, downsample_output, voxel_size):
                self.log_warning("Пропуск даунсемплинга")
            else:
                current_file = downsample_output
                self.last_outputs["downsampled"] = downsample_output

        self.last_outputs["final"] = current_file
        
        self.log_success(f"PDAL конвейер завершен. Результат: {current_file}")
        return True
