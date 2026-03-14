"""
Модуль для управления путями и их совместимостью между Windows и Docker.
"""

from pathlib import Path, PureWindowsPath, PurePosixPath
from typing import Union, Optional
from .config import Config


class PathManager:
    """Менеджер для управления путями проекта."""
    
    _project_root: Optional[Path] = None
    
    @classmethod
    def set_project_root(cls, root: Union[str, Path]) -> None:
        """Устанавливает корневую папку проекта."""
        cls._project_root = Path(root)
    
    @classmethod
    def get_project_root(cls) -> Path:
        """Получает корневую папку проекта."""
        if cls._project_root is None:
            # По умолчанию это папка, содержащая src/
            cls._project_root = Path(__file__).parent.parent.parent
        return cls._project_root
    
    @classmethod
    def get_data_root(cls) -> Path:
        """Получает корневую папку с данными."""
        return cls.get_project_root() / "data"
    
    @classmethod
    def get_input_dir(cls) -> Path:
        """Получает папку входных данных."""
        input_dir = cls.get_data_root() / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        return input_dir
    
    @classmethod
    def get_output_dir(cls) -> Path:
        """Получает папку выходных данных."""
        output_dir = cls.get_data_root() / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir
    
    @classmethod
    def get_temp_dir(cls) -> Path:
        """Получает папку временных файлов."""
        temp_dir = cls.get_data_root() / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        return temp_dir
    
    @classmethod
    def get_logs_dir(cls) -> Path:
        """Получает папку логов."""
        logs_dir = cls.get_data_root() / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        return logs_dir
    
    @classmethod
    def get_ground_input_dir(cls) -> Path:
        """Получает папку с входными фото наземной съемки."""
        ground_dir = cls.get_input_dir() / "ground"
        ground_dir.mkdir(parents=True, exist_ok=True)
        return ground_dir
    
    @classmethod
    def get_drone_input_dir(cls) -> Path:
        """Получает папку с входными фото с дронов."""
        drone_dir = cls.get_input_dir() / "drone"
        drone_dir.mkdir(parents=True, exist_ok=True)
        return drone_dir
    
    @classmethod
    def to_windows_path(cls, path: Union[str, Path]) -> str:
        """Преобразует путь в Windows формат."""
        return str(PureWindowsPath(path))
    
    @classmethod
    def to_posix_path(cls, path: Union[str, Path]) -> str:
        """Преобразует путь в POSIX формат (для Docker/Linux)."""
        return str(PurePosixPath(path))
    
    @classmethod
    def to_docker_path(cls, windows_path: Union[str, Path]) -> str:
        """
        Преобразует Windows путь в путь для Docker контейнера.
        
        Для ODM в Docker:
        C:\PointCloud\data\input -> /data/input
        
        Args:
            windows_path: Windows путь
            
        Returns:
            Путь, совместимый с Docker контейнером
        """
        path = Path(windows_path)
        
        # Если это путь к данным проекта
        data_root = cls.get_data_root()
        
        try:
            relative = path.relative_to(data_root)
            return f"/data/{relative.as_posix()}"
        except ValueError:
            # Если путь не внутри data_root, просто преобразуем
            # (это может быть путь вне проекта)
            return cls.to_posix_path(windows_path)


# Глобальный экземпляр менеджера путей
_path_manager = PathManager()


def get_path_manager() -> PathManager:
    """Возвращает глобальный экземпляр менеджера путей."""
    return _path_manager
