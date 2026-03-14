"""
Адаптер для Open3D - визуализации и обработки облаков точек.
"""

import numpy as np
from pathlib import Path
from typing import Optional, Tuple, List, Dict

from .base_adapter import BaseAdapter
from src.core import get_config, get_logger


class Open3DProcessor(BaseAdapter):
    """Адаптер для работы с Open3D."""
    
    def __init__(self):
        """Инициализирует Open3D адаптер."""
        super().__init__("Open3D")
        self.o3d = None
        self.pcd = None  # Текущее облако точек
        self._initialize_open3d()
    
    def _initialize_open3d(self) -> None:
        """Инициализирует Open3D модуль."""
        try:
            import open3d as o3d
            self.o3d = o3d
            self.log_success(f"Open3D инициализирован (версия {o3d.__version__})")
        except ImportError as e:
            self.log_error(f"Open3D не установлен: {e}")
    
    def is_available(self) -> bool:
        """Проверяет, доступен ли Open3D."""
        available = self.o3d is not None
        if not available:
            self.log_error("Open3D не доступен (не установлен)")
        return available

    def _read_point_cloud(self, file_path: Path):
        """Читает облако из файла и возвращает объект PointCloud."""
        file_path = Path(file_path)
        suffix = file_path.suffix.lower()

        if suffix in ['.ply', '.pcd']:
            return self.o3d.io.read_point_cloud(str(file_path))

        if suffix in ['.las', '.laz']:
            pcd = self.o3d.geometry.PointCloud()

            try:
                import laspy

                las = laspy.read(str(file_path))
                points = np.vstack((
                    np.asarray(las.x, dtype=np.float64),
                    np.asarray(las.y, dtype=np.float64),
                    np.asarray(las.z, dtype=np.float64),
                )).T
                pcd.points = self.o3d.utility.Vector3dVector(points)

                if all(hasattr(las, channel) for channel in ['red', 'green', 'blue']):
                    colors = np.vstack((
                        np.asarray(las.red, dtype=np.float64),
                        np.asarray(las.green, dtype=np.float64),
                        np.asarray(las.blue, dtype=np.float64),
                    )).T
                    max_val = np.max(colors)
                    if max_val > 0:
                        colors /= max_val
                    pcd.colors = self.o3d.utility.Vector3dVector(colors)

                return pcd

            except Exception:
                try:
                    import pdal

                    pipeline = pdal.Reader(str(file_path)).pipeline()
                    pipeline.execute()
                    arrays = pipeline.arrays
                    if not arrays:
                        self.log_error(f"PDAL не вернул точки из файла: {file_path}")
                        return None

                    arr = arrays[0]
                    pcd.points = self.o3d.utility.Vector3dVector(
                        np.column_stack((arr['X'], arr['Y'], arr['Z']))
                    )
                    return pcd

                except ImportError:
                    self.log_error("Для чтения LAS/LAZ требуется laspy или pdal")
                    return None

        self.log_error(
            f"Неподдерживаемый формат: {suffix}. Поддерживаются: .ply, .pcd, .las, .laz"
        )
        return None
    
    def load_point_cloud(self, file_path: Path) -> bool:
        """
        Загружает облако точек из файла.
        
        Args:
            file_path: Путь к файлу (ply, pcd, las, laz и т.д.)
            
        Returns:
            True если успешно загружено
        """
        if not self.is_available():
            return False
        
        file_path = Path(file_path)
        
        if not file_path.exists():
            self.log_error(f"Файл не найден: {file_path}")
            return False
        
        try:
            self.log_info(f"Загрузка облака точек из {file_path}...")

            self.pcd = self._read_point_cloud(file_path)
            if self.pcd is None:
                return False
            
            num_points = len(self.pcd.points)
            self.log_success(f"Облако точек загружено ({num_points} точек)")
            return True
            
        except Exception as e:
            self.log_error(f"Ошибка при загрузке облака: {e}")
            return False
    
    def compute_normals(
        self,
        radius_normal: Optional[float] = None,
        max_nn: Optional[int] = None,
        **kwargs
    ) -> bool:
        """
        Вычисляет нормали для облака точек.
        
        Args:
            radius_normal: Радиус поиска соседей (в метрах)
            max_nn: Максимальное количество соседей
            **kwargs: Дополнительные параметры
            
        Returns:
            True если успешно
        """
        if not self.is_available() or self.pcd is None:
            self.log_error("Облако точек не загружено")
            return False
        
        config = get_config()
        if radius_normal is None:
            radius_normal = config.get("open3d.processing.normals.radius_normal", 0.1)
        if max_nn is None:
            max_nn = config.get("open3d.processing.normals.max_nn", 30)
        
        self.log_info(f"Вычисление нормалей (radius={radius_normal}, max_nn={max_nn})...")
        
        try:
            # Используем KDTree для поиска соседей
            tree = self.o3d.geometry.KDTreeFlann(self.pcd)
            self.pcd.normals = self.o3d.utility.Vector3dVector(
                np.zeros((len(self.pcd.points), 3))
            )
            
            # Вычисляем нормали с помощью встроенного метода
            self.pcd.estimate_normals(
                search_param=self.o3d.geometry.KDTreeSearchParamHybrid(
                    radius=radius_normal,
                    max_nn=max_nn
                )
            )
            
            self.log_success("Нормали вычислены успешно")
            return True
            
        except Exception as e:
            self.log_error(f"Ошибка при вычислении нормалей: {e}")
            return False
    
    def downsampling(
        self,
        voxel_size: Optional[float] = None,
        **kwargs
    ) -> bool:
        """
        Выполняет вокселизацию облака (даунсемплинг).
        
        Args:
            voxel_size: Размер вокселя
            **kwargs: Дополнительные параметры
            
        Returns:
            True если успешно
        """
        if not self.is_available() or self.pcd is None:
            self.log_error("Облако точек не загружено")
            return False
        
        config = get_config()
        if voxel_size is None:
            voxel_size = config.get("open3d.processing.voxel_size", 0.05)
        
        original_count = len(self.pcd.points)
        
        self.log_info(f"Вокселизация облака (размер: {voxel_size})...")
        
        try:
            self.pcd = self.pcd.voxel_down_sample(voxel_size)
            
            new_count = len(self.pcd.points)
            ratio = (1 - new_count / original_count) * 100
            
            self.log_success(
                f"Даунсемплинг завершен ({original_count} -> {new_count} точек, "
                f"сокращение на {ratio:.1f}%)"
            )
            return True
            
        except Exception as e:
            self.log_error(f"Ошибка при даунсемплинге: {e}")
            return False
    
    def visualize(self, title: str = "Point Cloud") -> None:
        """
        Визуализирует облако точек.
        
        Args:
            title: Заголовок окна визуализации
        """
        if not self.is_available() or self.pcd is None:
            self.log_error("Облако точек не загружено")
            return
        
        config = get_config()
        point_size = config.get("open3d.visualization.point_size", 2.0)
        
        self.log_info(f"Открытие визуализации ({len(self.pcd.points)} точек)...")
        
        try:
            vis = self.o3d.visualization.Visualizer()
            vis.create_window(window_name=title, width=800, height=600)
            vis.add_geometry(self.pcd)
            
            # Опционально добавляем coordinate frame
            show_frame = config.get("open3d.visualization.show_coordinate_frame", True)
            if show_frame:
                frame = self.o3d.geometry.TriangleMesh.create_coordinate_frame(
                    size=0.5,
                    origin=[0, 0, 0]
                )
                vis.add_geometry(frame)
            
            # Рендер и закрытие
            vis.run()
            vis.destroy_window()
            
            self.log_success("Визуализация завершена")
            
        except Exception as e:
            self.log_error(f"Ошибка при визуализации: {e}")

    def visualize_layers(
        self,
        layer_files: Dict[str, Path],
        selected_layers: Optional[List[str]] = None,
        title: str = "Point Cloud Layers",
    ) -> None:
        """
        Визуализирует несколько слоев с возможностью их переключения.

        Управление:
        - клавиши 1..9: включить/выключить соответствующий слой
        """
        if not self.is_available():
            self.log_error("Open3D недоступен")
            return

        existing_layers = {
            name: Path(path)
            for name, path in layer_files.items()
            if path is not None and Path(path).exists()
        }

        if not existing_layers:
            self.log_error("Нет доступных слоев для визуализации")
            return

        selected = set(selected_layers or existing_layers.keys())
        points_by_layer = {}

        # Базовая палитра для семантических слоев.
        layer_colors = {
            "ground": [0.55, 0.42, 0.25],
            "vegetation": [0.18, 0.65, 0.22],
            "outliers": [0.95, 0.10, 0.10],
            "no_ground": [0.20, 0.60, 0.95],
            "no_outliers": [0.75, 0.75, 0.75],
            "final": [0.85, 0.85, 0.85],
        }

        for name, path in existing_layers.items():
            cloud = self._read_point_cloud(path)
            if cloud is None:
                continue

            if len(cloud.points) == 0:
                self.log_warning(f"Слой '{name}' пустой: {path}")
                continue

            if not cloud.has_colors() and name in layer_colors:
                cloud.paint_uniform_color(layer_colors[name])

            points_by_layer[name] = cloud

        if not points_by_layer:
            self.log_error("Не удалось загрузить ни один слой для визуализации")
            return

        layer_names = list(points_by_layer.keys())
        visibility = {name: (name in selected) for name in layer_names}

        if not any(visibility.values()):
            visibility[layer_names[0]] = True

        try:
            vis = self.o3d.visualization.VisualizerWithKeyCallback()
            vis.create_window(window_name=title, width=1280, height=800)

            def toggle_layer(layer_name: str):
                def _cb(_):
                    if visibility[layer_name]:
                        vis.remove_geometry(points_by_layer[layer_name], reset_bounding_box=False)
                    else:
                        vis.add_geometry(points_by_layer[layer_name], reset_bounding_box=False)
                    visibility[layer_name] = not visibility[layer_name]
                    state = "ON" if visibility[layer_name] else "OFF"
                    self.log_info(f"Слой '{layer_name}': {state}")
                    return False
                return _cb

            first_added = False
            for idx, name in enumerate(layer_names):
                if visibility[name]:
                    vis.add_geometry(points_by_layer[name], reset_bounding_box=not first_added)
                    first_added = True

                if idx < 9:
                    vis.register_key_callback(ord(str(idx + 1)), toggle_layer(name))

            config = get_config()
            show_frame = config.get("open3d.visualization.show_coordinate_frame", True)
            if show_frame:
                frame = self.o3d.geometry.TriangleMesh.create_coordinate_frame(size=0.5, origin=[0, 0, 0])
                vis.add_geometry(frame)

            self.log_info("Управление слоями: 1..9 - вкл/выкл слой")
            for idx, name in enumerate(layer_names[:9], start=1):
                default_state = "ON" if visibility[name] else "OFF"
                self.log_info(f"  [{idx}] {name} ({default_state})")

            vis.run()
            vis.destroy_window()
            self.log_success("Визуализация слоев завершена")

        except Exception as e:
            self.log_error(f"Ошибка при визуализации слоев: {e}")
    
    def save_point_cloud(self, output_path: Path) -> bool:
        """
        Сохраняет облако точек в файл.
        
        Args:
            output_path: Путь для сохранения
            
        Returns:
            True если успешно
        """
        if not self.is_available() or self.pcd is None:
            self.log_error("Облако точек не загружено")
            return False
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.log_info(f"Сохранение облака в {output_path}...")
        
        try:
            self.o3d.io.write_point_cloud(str(output_path), self.pcd)
            self.log_success(f"Облако сохранено: {output_path}")
            return True
            
        except Exception as e:
            self.log_error(f"Ошибка при сохранении: {e}")
            return False
    
    def execute(
        self,
        input_file: Path,
        output_dir: Path,
        **kwargs
    ) -> bool:
        """
        Выполняет полный конвейер обработки в Open3D.
        
        Args:
            input_file: Входной файл облака точек
            output_dir: Папка для сохранения результатов
            **kwargs: Дополнительные параметры
            
        Returns:
            True если успешно
        """
        if not self.is_available():
            return False
        
        input_file = Path(input_file)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Этап 1: Загрузка облака
        if not self.load_point_cloud(input_file):
            return False
        
        # Этап 2: Вокселизация
        config = get_config()
        if config.get("open3d.processing.voxel_size") is not None:
            self.log_info("Этап 1: Даунсемплинг...")
            voxel_size = config.get("open3d.processing.voxel_size")
            self.downsampling(voxel_size)
        
        # Этап 3: Вычисление нормалей
        if config.get("open3d.processing.normals.radius_normal") is not None:
            self.log_info("Этап 2: Вычисление нормалей...")
            self.compute_normals()
        
        # Этап 4: Сохранение
        output_file = output_dir / f"{input_file.stem}_processed.ply"
        self.log_info("Этап 3: Сохранение результата...")
        if not self.save_point_cloud(output_file):
            return False
        
        self.log_success(f"Open3D конвейер завершен. Результат: {output_file}")
        return True
