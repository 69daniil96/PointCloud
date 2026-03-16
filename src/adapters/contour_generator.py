"""
Адаптер для генерации изолиний (линий уровня) из облака точек.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .base_adapter import BaseAdapter
from src.core import get_config


class ContourGenerator(BaseAdapter):
    """Генератор изолиний из облака точек через регулярную сетку и marching squares."""

    # edge id -> (corner_a, corner_b)
    _EDGE_TO_CORNERS = {
        0: (0, 1),
        1: (1, 2),
        2: (2, 3),
        3: (3, 0),
    }

    # case index -> list[(edge_a, edge_b)]
    _CASE_SEGMENTS = {
        0: [],
        1: [(3, 0)],
        2: [(0, 1)],
        3: [(3, 1)],
        4: [(1, 2)],
        5: [(3, 2), (0, 1)],
        6: [(0, 2)],
        7: [(3, 2)],
        8: [(2, 3)],
        9: [(0, 2)],
        10: [(0, 3), (1, 2)],
        11: [(1, 2)],
        12: [(1, 3)],
        13: [(0, 1)],
        14: [(0, 3)],
        15: [],
    }

    def __init__(self):
        super().__init__("ContourGenerator")

    def is_available(self) -> bool:
        return True

    def _load_points(self, file_path: Path) -> Optional[np.ndarray]:
        """Загружает точки Nx3 из .las/.laz/.ply/.pcd."""
        file_path = Path(file_path)
        suffix = file_path.suffix.lower()

        try:
            if suffix in [".las", ".laz"]:
                try:
                    import laspy

                    las = laspy.read(str(file_path))
                    return np.vstack((
                        np.asarray(las.x, dtype=np.float64),
                        np.asarray(las.y, dtype=np.float64),
                        np.asarray(las.z, dtype=np.float64),
                    )).T
                except Exception:
                    import pdal

                    pipeline = pdal.Reader(str(file_path)).pipeline()
                    pipeline.execute()
                    arrays = pipeline.arrays
                    if not arrays:
                        return None
                    arr = arrays[0]
                    return np.column_stack((arr["X"], arr["Y"], arr["Z"]))

            if suffix in [".ply", ".pcd"]:
                import open3d as o3d

                cloud = o3d.io.read_point_cloud(str(file_path))
                return np.asarray(cloud.points, dtype=np.float64)

        except Exception as e:
            self.log_error(f"Ошибка загрузки точек из {file_path}: {e}")
            return None

        self.log_error(f"Неподдерживаемый формат для изолиний: {suffix}")
        return None

    def _build_grid(
        self,
        points: np.ndarray,
        grid_size: float,
        max_grid_cells: int,
    ) -> Optional[Tuple[np.ndarray, float, float, int, int]]:
        """Строит регулярную сетку средних высот Z."""
        x = points[:, 0]
        y = points[:, 1]
        z = points[:, 2]

        min_x, max_x = float(np.min(x)), float(np.max(x))
        min_y, max_y = float(np.min(y)), float(np.max(y))

        nx = max(2, int(np.ceil((max_x - min_x) / grid_size)) + 1)
        ny = max(2, int(np.ceil((max_y - min_y) / grid_size)) + 1)

        if nx * ny > max_grid_cells:
            self.log_error(
                f"Сетка слишком большая: {nx}x{ny} ({nx * ny} ячеек), лимит {max_grid_cells}"
            )
            return None

        ix = np.clip(((x - min_x) / grid_size).astype(np.int32), 0, nx - 1)
        iy = np.clip(((y - min_y) / grid_size).astype(np.int32), 0, ny - 1)
        flat_idx = iy * nx + ix

        sums = np.bincount(flat_idx, weights=z, minlength=nx * ny)
        counts = np.bincount(flat_idx, minlength=nx * ny)

        grid = np.full(nx * ny, np.nan, dtype=np.float64)
        valid = counts > 0
        grid[valid] = sums[valid] / counts[valid]
        grid = grid.reshape((ny, nx))

        return grid, min_x, min_y, nx, ny

    def _fill_nans(self, grid: np.ndarray, iterations: int = 4) -> np.ndarray:
        """Грубое заполнение дыр в сетке средним соседей."""
        filled = grid.copy()

        for _ in range(iterations):
            nan_mask = np.isnan(filled)
            if not np.any(nan_mask):
                break

            updated = filled.copy()
            h, w = filled.shape

            for y in range(h):
                y0 = max(0, y - 1)
                y1 = min(h, y + 2)
                for x in range(w):
                    if not nan_mask[y, x]:
                        continue
                    x0 = max(0, x - 1)
                    x1 = min(w, x + 2)
                    neigh = filled[y0:y1, x0:x1]
                    neigh = neigh[~np.isnan(neigh)]
                    if neigh.size > 0:
                        updated[y, x] = float(np.mean(neigh))

            filled = updated

        return filled

    def _interpolate_edge_point(
        self,
        corners_xy: List[Tuple[float, float]],
        corners_z: List[float],
        edge_id: int,
        level: float,
    ) -> Tuple[float, float, float]:
        """Интерполирует пересечение изолинии с ребром клетки."""
        c0, c1 = self._EDGE_TO_CORNERS[edge_id]
        x0, y0 = corners_xy[c0]
        x1, y1 = corners_xy[c1]
        z0 = corners_z[c0]
        z1 = corners_z[c1]

        if np.isclose(z1, z0):
            t = 0.5
        else:
            t = (level - z0) / (z1 - z0)
            t = float(np.clip(t, 0.0, 1.0))

        x = x0 + t * (x1 - x0)
        y = y0 + t * (y1 - y0)
        return (float(x), float(y), float(level))

    def _generate_segments(
        self,
        grid: np.ndarray,
        min_x: float,
        min_y: float,
        grid_size: float,
        levels: np.ndarray,
    ) -> List[Dict[str, Any]]:
        """Строит сегменты изолиний методом marching squares."""
        segments: List[Dict[str, Any]] = []
        ny, nx = grid.shape

        for level in levels:
            for y in range(ny - 1):
                y0 = min_y + y * grid_size
                y1 = y0 + grid_size

                for x in range(nx - 1):
                    x0 = min_x + x * grid_size
                    x1 = x0 + grid_size

                    z00 = grid[y, x]
                    z10 = grid[y, x + 1]
                    z11 = grid[y + 1, x + 1]
                    z01 = grid[y + 1, x]

                    if np.isnan([z00, z10, z11, z01]).any():
                        continue

                    corners_z = [float(z00), float(z10), float(z11), float(z01)]
                    corners_xy = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

                    case = 0
                    if z00 >= level:
                        case |= 1
                    if z10 >= level:
                        case |= 2
                    if z11 >= level:
                        case |= 4
                    if z01 >= level:
                        case |= 8

                    edge_pairs = self._CASE_SEGMENTS.get(case, [])
                    for e0, e1 in edge_pairs:
                        p0 = self._interpolate_edge_point(corners_xy, corners_z, e0, float(level))
                        p1 = self._interpolate_edge_point(corners_xy, corners_z, e1, float(level))
                        segments.append({
                            "level": float(level),
                            "start": [p0[0], p0[1], p0[2]],
                            "end": [p1[0], p1[1], p1[2]],
                        })

        return segments

    def generate_from_point_cloud(
        self,
        input_file: Path,
        output_file: Path,
        interval: Optional[float] = None,
        grid_size: Optional[float] = None,
        apply_random_georef: bool = False,
        random_seed: Optional[int] = None,
        random_shift_m: Optional[float] = None,
        **kwargs,
    ) -> bool:
        """Генерирует изолинии из облака точек и сохраняет в JSON."""
        input_file = Path(input_file)
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        config = get_config()
        interval_value = float(interval if interval is not None else config.get("contours.interval", 1.0))
        grid_size_value = float(grid_size if grid_size is not None else config.get("contours.grid_size", 1.0))
        random_seed_value = int(random_seed if random_seed is not None else config.get("contours.random_seed", 42))
        random_shift_value = float(
            random_shift_m if random_shift_m is not None else config.get("contours.random_shift_m", 5000.0)
        )
        max_grid_cells = int(config.get("contours.max_grid_cells", 1200000))

        if interval_value <= 0 or grid_size_value <= 0:
            self.log_error("Параметры interval и grid_size должны быть > 0")
            return False

        points = self._load_points(input_file)
        if points is None or points.shape[0] < 10:
            self.log_error("Недостаточно точек для построения изолиний")
            return False

        if apply_random_georef:
            rng = np.random.default_rng(random_seed_value)
            dx = float(rng.uniform(-random_shift_value, random_shift_value))
            dy = float(rng.uniform(-random_shift_value, random_shift_value))
            points = points.copy()
            points[:, 0] += dx
            points[:, 1] += dy
            self.log_info(f"Применена псевдо-случайная геопривязка: dx={dx:.2f}, dy={dy:.2f}")

        built = self._build_grid(points, grid_size=grid_size_value, max_grid_cells=max_grid_cells)
        if built is None:
            return False

        grid, min_x, min_y, nx, ny = built
        grid = self._fill_nans(grid)

        valid_z = grid[~np.isnan(grid)]
        if valid_z.size == 0:
            self.log_error("После интерполяции сетка пустая")
            return False

        min_z = float(np.min(valid_z))
        max_z = float(np.max(valid_z))

        level_start = np.floor(min_z / interval_value) * interval_value
        level_end = np.ceil(max_z / interval_value) * interval_value
        levels = np.arange(level_start, level_end + interval_value * 0.5, interval_value, dtype=np.float64)

        segments = self._generate_segments(
            grid=grid,
            min_x=min_x,
            min_y=min_y,
            grid_size=grid_size_value,
            levels=levels,
        )

        result = {
            "metadata": {
                "source": str(input_file),
                "interval": float(interval_value),
                "grid_size": float(grid_size_value),
                "random_georef_applied": bool(apply_random_georef),
                "grid_shape": [int(ny), int(nx)],
                "z_range": [min_z, max_z],
            },
            "levels": [float(v) for v in levels.tolist()],
            "segment_count": int(len(segments)),
            "segments": segments,
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        self.log_success(
            f"Изолинии построены: {output_file} (уровней={len(levels)}, сегментов={len(segments)})"
        )
        return True

    def execute(self, input_file: Path, output_dir: Path, **kwargs) -> bool:
        """Стандартный интерфейс BaseAdapter.execute."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{Path(input_file).stem}_contours.json"
        return self.generate_from_point_cloud(input_file, output_file, **kwargs)
