"""
Адаптер для Open3D - визуализации и обработки облаков точек.
"""

import json
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

    def _elevation_to_color(self, z_value: float, z_min: float, z_max: float) -> List[float]:
        """Преобразует высоту в цвет: низины (синий) -> средние (зеленый) -> вершины (красный)."""
        if np.isclose(z_max, z_min):
            return [0.2, 0.75, 0.3]

        t = float((z_value - z_min) / (z_max - z_min))
        t = float(np.clip(t, 0.0, 1.0))

        if t < 0.5:
            # Blue -> Green
            a = t / 0.5
            return [0.1 * (1 - a) + 0.2 * a, 0.35 * (1 - a) + 0.8 * a, 0.9 * (1 - a) + 0.2 * a]

        # Green -> Red
        a = (t - 0.5) / 0.5
        return [0.2 * (1 - a) + 0.9 * a, 0.8 * (1 - a) + 0.2 * a, 0.2 * (1 - a) + 0.1 * a]

    def _read_contours_lineset(self, file_path: Path, relief_coloring: bool = True):
        """Читает JSON изолиний и возвращает Open3D LineSet."""
        file_path = Path(file_path)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            segments = data.get("segments", [])
            if not segments:
                return None

            z_range = data.get("metadata", {}).get("z_range", None)
            if isinstance(z_range, list) and len(z_range) == 2:
                z_min = float(z_range[0])
                z_max = float(z_range[1])
            else:
                levels = [float(seg.get("level", 0.0)) for seg in segments]
                if levels:
                    z_min = float(np.min(levels))
                    z_max = float(np.max(levels))
                else:
                    z_min, z_max = 0.0, 1.0

            points = []
            lines = []
            colors = []

            for segment in segments:
                start = segment.get("start")
                end = segment.get("end")
                if not start or not end:
                    continue

                i0 = len(points)
                points.append([float(start[0]), float(start[1]), float(start[2])])
                i1 = len(points)
                points.append([float(end[0]), float(end[1]), float(end[2])])
                lines.append([i0, i1])

                if relief_coloring:
                    seg_z = float(segment.get("level", (start[2] + end[2]) * 0.5))
                    colors.append(self._elevation_to_color(seg_z, z_min, z_max))
                else:
                    colors.append([1.0, 0.65, 0.1])

            if not points or not lines:
                return None

            line_set = self.o3d.geometry.LineSet()
            line_set.points = self.o3d.utility.Vector3dVector(np.asarray(points, dtype=np.float64))
            line_set.lines = self.o3d.utility.Vector2iVector(np.asarray(lines, dtype=np.int32))
            line_set.colors = self.o3d.utility.Vector3dVector(np.asarray(colors, dtype=np.float64))
            return line_set

        except Exception as e:
            self.log_error(f"Ошибка чтения изолиний {file_path}: {e}")
            return None

    def _build_thick_lineset(self, line_set, thickness_ratio: float = 3.0):
        """Создает более толстый вариант LineSet через дублирование линий с малыми XY-смещениями."""
        if line_set is None:
            return None

        try:
            points = np.asarray(line_set.points, dtype=np.float64)
            lines = np.asarray(line_set.lines, dtype=np.int32)
            colors = np.asarray(line_set.colors, dtype=np.float64)

            if points.size == 0 or lines.size == 0:
                return line_set

            x_span = float(np.max(points[:, 0]) - np.min(points[:, 0]))
            y_span = float(np.max(points[:, 1]) - np.min(points[:, 1]))
            scale = max(x_span, y_span, 1.0)

            ratio = max(1.0, float(thickness_ratio))
            eps = scale * 0.0002 * ratio
            eps = min(max(eps, 0.002), 0.2)

            offsets = [
                (0.0, 0.0),
                (eps, 0.0),
                (-eps, 0.0),
                (0.0, eps),
                (0.0, -eps),
            ]

            merged_points = []
            merged_lines = []
            merged_colors = []

            for dx, dy in offsets:
                base_idx = len(merged_points)
                shifted = points.copy()
                shifted[:, 0] += dx
                shifted[:, 1] += dy
                merged_points.extend(shifted.tolist())
                merged_lines.extend((lines + base_idx).tolist())
                merged_colors.extend(colors.tolist())

            thick = self.o3d.geometry.LineSet()
            thick.points = self.o3d.utility.Vector3dVector(np.asarray(merged_points, dtype=np.float64))
            thick.lines = self.o3d.utility.Vector2iVector(np.asarray(merged_lines, dtype=np.int32))
            thick.colors = self.o3d.utility.Vector3dVector(np.asarray(merged_colors, dtype=np.float64))
            return thick

        except Exception as e:
            self.log_warning(f"Не удалось построить толстые изолинии: {e}")
            return line_set
    
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
        - клавиши 1..9: включить/выключить слой (только в режиме облака)
        - клавиша C: переключить режимы CLOUD <-> CONTOURS
        - клавиша R: вкл/выкл цветной рельеф изолиний (только в режиме изолиний)
        - клавиша T: тонкие/толстые линии изолиний (только в режиме изолиний)
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
        config = get_config()
        contour_relief_enabled = bool(
            config.get("open3d.visualization.contour_relief_enabled", True)
        )
        contour_line_width_thin = float(
            config.get("open3d.visualization.contour_line_width_thin", 1.0)
        )
        contour_line_width_thick = float(
            config.get("open3d.visualization.contour_line_width_thick", 3.0)
        )
        contour_thickness_ratio = max(1.0, contour_line_width_thick / max(contour_line_width_thin, 0.1))
        contour_line_width_thick_mode = False

        point_geometry_by_layer = {}
        contours_path = existing_layers.get("contours")

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
            if name == "contours":
                continue

            cloud = self._read_point_cloud(path)
            if cloud is None:
                continue

            if len(cloud.points) == 0:
                self.log_warning(f"Слой '{name}' пустой: {path}")
                continue

            if not cloud.has_colors() and name in layer_colors:
                cloud.paint_uniform_color(layer_colors[name])

            point_geometry_by_layer[name] = cloud

        contour_geometry_relief = None
        contour_geometry_flat = None
        contour_geometry_relief_thick = None
        contour_geometry_flat_thick = None
        if contours_path is not None and Path(contours_path).suffix.lower() == ".json":
            contour_geometry_relief = self._read_contours_lineset(contours_path, relief_coloring=True)
            contour_geometry_flat = self._read_contours_lineset(contours_path, relief_coloring=False)

            if contour_geometry_relief is not None:
                contour_geometry_relief_thick = self._build_thick_lineset(
                    contour_geometry_relief,
                    thickness_ratio=contour_thickness_ratio,
                )
            if contour_geometry_flat is not None:
                contour_geometry_flat_thick = self._build_thick_lineset(
                    contour_geometry_flat,
                    thickness_ratio=contour_thickness_ratio,
                )

            if contour_geometry_relief is None and contour_geometry_flat is None:
                self.log_warning(f"Слой 'contours' не удалось загрузить: {contours_path}")

        has_contours = contour_geometry_relief is not None or contour_geometry_flat is not None
        if not point_geometry_by_layer and not has_contours:
            self.log_error("Не удалось загрузить ни один слой для визуализации")
            return

        point_layer_names = list(point_geometry_by_layer.keys())
        point_visibility = {name: (name in selected) for name in point_layer_names}

        if point_layer_names and not any(point_visibility.values()):
            point_visibility[point_layer_names[0]] = True

        selected_has_non_contours = any(layer_name != "contours" for layer_name in selected)
        if has_contours and not selected_has_non_contours and "contours" in selected:
            current_mode = "contour"
        elif point_layer_names:
            current_mode = "point"
        else:
            current_mode = "contour"

        try:
            vis = self.o3d.visualization.VisualizerWithKeyCallback()
            vis.create_window(window_name=title, width=1280, height=800)

            def get_active_contour_geometry():
                if contour_relief_enabled:
                    candidate = contour_geometry_relief_thick if contour_line_width_thick_mode else contour_geometry_relief
                else:
                    candidate = contour_geometry_flat_thick if contour_line_width_thick_mode else contour_geometry_flat

                if candidate is None:
                    if contour_line_width_thick_mode:
                        if contour_relief_enabled:
                            return contour_geometry_relief_thick or contour_geometry_relief or contour_geometry_flat
                        return contour_geometry_flat_thick or contour_geometry_flat or contour_geometry_relief
                    if contour_relief_enabled:
                        return contour_geometry_relief or contour_geometry_flat
                    return contour_geometry_flat or contour_geometry_relief

                return candidate

            contour_geometry_current = get_active_contour_geometry()

            contour_visible = False

            def apply_contour_line_width() -> None:
                if current_mode != "contour":
                    return
                try:
                    render_opt = vis.get_render_option()
                    render_opt.line_width = (
                        contour_line_width_thick if contour_line_width_thick_mode else contour_line_width_thin
                    )
                except Exception:
                    # На части бэкендов Open3D толщина линий может быть зафиксирована драйвером.
                    pass

            def add_point_layer(layer_name: str) -> None:
                vis.add_geometry(point_geometry_by_layer[layer_name], reset_bounding_box=False)

            def remove_point_layer(layer_name: str) -> None:
                vis.remove_geometry(point_geometry_by_layer[layer_name], reset_bounding_box=False)

            def set_mode(new_mode: str) -> None:
                nonlocal current_mode, contour_visible
                if new_mode == current_mode:
                    return

                if new_mode == "contour" and not has_contours:
                    self.log_info("Слой 'contours' недоступен")
                    return

                if new_mode == "point" and not point_layer_names:
                    self.log_info("Облачные слои недоступны")
                    return

                if current_mode == "point":
                    for layer_name in point_layer_names:
                        if point_visibility[layer_name]:
                            remove_point_layer(layer_name)
                elif current_mode == "contour" and contour_visible and contour_geometry_current is not None:
                    vis.remove_geometry(contour_geometry_current, reset_bounding_box=False)
                    contour_visible = False

                if new_mode == "point":
                    for layer_name in point_layer_names:
                        if point_visibility[layer_name]:
                            add_point_layer(layer_name)
                    self.log_info("Режим визуализации: CLOUD")
                else:
                    if contour_geometry_current is not None:
                        vis.add_geometry(contour_geometry_current, reset_bounding_box=False)
                        contour_visible = True
                        apply_contour_line_width()
                    self.log_info("Режим визуализации: CONTOURS")

                current_mode = new_mode

            def toggle_layer(layer_name: str):
                def _cb(_):
                    if current_mode != "point":
                        self.log_info("Клавиши фильтров отключены в режиме CONTOURS")
                        return False

                    if point_visibility[layer_name]:
                        remove_point_layer(layer_name)
                    else:
                        add_point_layer(layer_name)
                    point_visibility[layer_name] = not point_visibility[layer_name]
                    state = "ON" if point_visibility[layer_name] else "OFF"
                    self.log_info(f"Слой '{layer_name}': {state}")
                    return False
                return _cb

            def toggle_mode(_):
                if current_mode == "point":
                    set_mode("contour")
                else:
                    set_mode("point")
                return False

            def toggle_contour_relief(_):
                nonlocal contour_relief_enabled, contour_geometry_current, contour_visible

                if current_mode != "contour":
                    self.log_info("Клавиши изолиний отключены в режиме CLOUD")
                    return False

                if contour_geometry_relief is None or contour_geometry_flat is None:
                    self.log_info("Цветной рельеф изолиний недоступен")
                    return False

                if contour_visible and contour_geometry_current is not None:
                    vis.remove_geometry(contour_geometry_current, reset_bounding_box=False)

                contour_relief_enabled = not contour_relief_enabled
                contour_geometry_current = get_active_contour_geometry()

                if contour_geometry_current is not None:
                    vis.add_geometry(contour_geometry_current, reset_bounding_box=False)
                    contour_visible = True

                state = "ON" if contour_relief_enabled else "OFF"
                self.log_info(f"Цветной рельеф изолиний: {state}")
                return False

            def toggle_contour_line_width(_):
                nonlocal contour_line_width_thick_mode, contour_geometry_current, contour_visible

                if current_mode != "contour":
                    self.log_info("Клавиши изолиний отключены в режиме CLOUD")
                    return False

                if contour_geometry_current is None:
                    self.log_info("Слой изолиний недоступен")
                    return False

                if contour_visible:
                    vis.remove_geometry(contour_geometry_current, reset_bounding_box=False)

                contour_line_width_thick_mode = not contour_line_width_thick_mode
                contour_geometry_current = get_active_contour_geometry()

                if contour_geometry_current is not None:
                    vis.add_geometry(contour_geometry_current, reset_bounding_box=False)
                    contour_visible = True

                apply_contour_line_width()
                state = "THICK" if contour_line_width_thick_mode else "THIN"
                self.log_info(f"Толщина линий изолиний: {state}")
                return False

            first_added = False
            if current_mode == "point":
                for layer_name in point_layer_names:
                    if point_visibility[layer_name]:
                        vis.add_geometry(
                            point_geometry_by_layer[layer_name],
                            reset_bounding_box=not first_added,
                        )
                        first_added = True
            else:
                if contour_geometry_current is not None:
                    vis.add_geometry(contour_geometry_current, reset_bounding_box=not first_added)
                    contour_visible = True
                    first_added = True

            for idx, name in enumerate(point_layer_names):
                if idx < 9:
                    vis.register_key_callback(ord(str(idx + 1)), toggle_layer(name))

            vis.register_key_callback(ord('C'), toggle_mode)
            vis.register_key_callback(ord('c'), toggle_mode)
            vis.register_key_callback(ord('R'), toggle_contour_relief)
            vis.register_key_callback(ord('r'), toggle_contour_relief)
            vis.register_key_callback(ord('T'), toggle_contour_line_width)
            vis.register_key_callback(ord('t'), toggle_contour_line_width)

            show_frame = config.get("open3d.visualization.show_coordinate_frame", True)
            if show_frame:
                frame = self.o3d.geometry.TriangleMesh.create_coordinate_frame(size=0.5, origin=[0, 0, 0])
                vis.add_geometry(frame)

            self.log_info("Управление режимами: [C] CLOUD <-> CONTOURS")
            self.log_info("Управление CLOUD: 1..9 - вкл/выкл облачные слои")
            for idx, name in enumerate(point_layer_names[:9], start=1):
                default_state = "ON" if point_visibility[name] else "OFF"
                self.log_info(f"  [{idx}] {name} ({default_state})")

            if has_contours:
                relief_state = "ON" if contour_relief_enabled else "OFF"
                width_state = "THICK" if contour_line_width_thick_mode else "THIN"
                self.log_info("Управление CONTOURS: [R] цветной рельеф изолиний")
                self.log_info("Управление CONTOURS: [T] толщина линий изолиний")
                self.log_info(f"  contours (relief={relief_state}, width={width_state})")

            self.log_info(
                "Ограничение режимов: в CONTOURS отключены клавиши фильтров, "
                "в CLOUD отключены клавиши изолиний"
            )

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
