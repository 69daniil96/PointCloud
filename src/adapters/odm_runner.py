"""
Адаптер для ODM (OpenDroneMap) - инструмента обработки аэрофотографий.
"""

import json
import subprocess
import time
from pathlib import Path
from typing import Optional, Dict, Any, List

from .base_adapter import BaseAdapter
from src.core import get_config, get_logger


class ODMRunner(BaseAdapter):
    """Адаптер для запуска ODM через Docker."""
    
    def __init__(self):
        """Инициализирует ODM адаптер."""
        super().__init__("ODM")
        self.docker_image: str = "opendronemap/odm:latest"
        self.container_name: str = "odm_processor"
        self._check_docker_config()
    
    def _check_docker_config(self) -> None:
        """Проверяет конфигурацию Docker."""
        config = get_config()
        self.docker_image = config.get("odm.docker_image", "opendronemap/odm:latest")
        self.container_name = config.get("odm.docker_container_name", "odm_processor")
    
    def is_available(self) -> bool:
        """Проверяет, доступен ли Docker и образ ODM."""
        try:
            # Проверяем, установлен ли Docker
            result = subprocess.run(
                ["docker", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                self.log_error("Docker не установлен или не запущен")
                return False
            
            self.log_success(f"Docker найден: {result.stdout.strip()}")

            # Проверяем, что Docker daemon доступен.
            # Для Windows это стабильнее через docker version (Server).
            daemon = None
            for _ in range(3):
                daemon = subprocess.run(
                    ["docker", "version", "--format", "{{.Server.Version}}"],
                    capture_output=True,
                    text=True,
                    timeout=8,
                )
                if daemon.returncode == 0 and daemon.stdout.strip():
                    break
                time.sleep(1)

            if daemon is None:
                self.log_error("Не удалось выполнить проверку Docker daemon")
                return False

            if daemon.returncode != 0:
                details = (daemon.stderr or daemon.stdout or "").strip()
                self.log_error(
                    "Docker daemon недоступен. Убедитесь, что Docker Desktop запущен "
                    "и Engine имеет статус running."
                )
                if details:
                    self.log_error(f"Детали Docker: {details[:500]}")
                return False
            
            # Проверяем наличие образа ODM
            result = subprocess.run(
                ["docker", "image", "inspect", self.docker_image],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if self.is_image_available():
                self.log_success(f"Образ ODM найден: {self.docker_image}")
            else:
                self.log_info(f"Образ ODM не найден. Его нужно загрузить: {self.docker_image}")

            # Для доступности адаптера достаточно, чтобы Docker был рабочим.
            return True
                
        except subprocess.TimeoutExpired:
            self.log_error("Timeout при проверке Docker")
            return False
        except Exception as e:
            self.log_error(f"Ошибка при проверке Docker: {e}")
            return False
    
    def pull_image(self) -> bool:
        """Загружает образ ODM из Docker Hub."""
        if not self._check_docker_available():
            return False
        
        self.log_info(f"Загрузка образа {self.docker_image}...")
        self.log_info("Это может занять несколько минут...")
        
        try:
            result = subprocess.run(
                ["docker", "pull", self.docker_image],
                check=False,
                timeout=300,  # 5 минут timeout
            )
            
            if result.returncode == 0:
                self.log_success(f"Образ успешно загружен: {self.docker_image}")
                return True
            else:
                self.log_error("Ошибка при загрузке образа")
                if result.stderr:
                    self.log_error(f"Вывод Docker: {result.stderr[:500]}")
                return False
                
        except subprocess.TimeoutExpired:
            self.log_error("Timeout при загрузке образа (слишком долго)")
            return False
        except Exception as e:
            self.log_error(f"Ошибка при загрузке образа: {e}")
            return False
    
    def _check_docker_available(self) -> bool:
        """Внутренняя проверка наличия Docker."""
        try:
            version = subprocess.run(
                ["docker", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True
            )
            if version.returncode != 0:
                return False

            daemon = None
            for _ in range(3):
                daemon = subprocess.run(
                    ["docker", "version", "--format", "{{.Server.Version}}"],
                    capture_output=True,
                    text=True,
                    timeout=8,
                )
                if daemon.returncode == 0 and daemon.stdout.strip():
                    return True
                time.sleep(1)

            return False
        except:
            return False

    def is_image_available(self) -> bool:
        """Проверяет, загружен ли Docker образ ODM локально."""
        try:
            result = subprocess.run(
                ["docker", "image", "inspect", self.docker_image],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                return True

            # Fallback: на Windows inspect иногда даёт ложный non-zero сразу после pull.
            fallback = subprocess.run(
                ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if fallback.returncode != 0:
                return False

            images = {line.strip() for line in fallback.stdout.splitlines() if line.strip()}
            return self.docker_image in images

        except Exception:
            return False
    
    def execute(
        self,
        image_dir: Path,
        output_dir: Path,
        **kwargs
    ) -> bool:
        """
        Выполняет обработку фото с дронов через ODM.
        
        Args:
            image_dir: Папка с фотографиями дронов
            output_dir: Папка для сохранения результатов
            **kwargs: Дополнительные параметры ODM
            
        Returns:
            True если успешно
        """
        if not self.is_available():
            self.log_error("ODM (Docker) не доступен")
            return False
        
        image_dir = Path(image_dir).resolve()
        output_dir = Path(output_dir).resolve()
        
        # Убеждаемся, что папки существуют
        if not image_dir.exists():
            self.log_error(f"Папка с изображениями не найдена: {image_dir}")
            return False
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # ODM ожидает структуру: <project-path>/<dataset>/images
        docker_project_path = "/datasets"
        docker_dataset_name = "code"
        docker_images_path = f"{docker_project_path}/{docker_dataset_name}/images"
        
        config = get_config()
        
        # Параметры обработки
        min_num_features = config.get("odm.processing.min_num_features", 4000)
        feature_quality = config.get("odm.processing.feature_quality", "high")
        
        # Формируем команду Docker
        docker_command = [
            "docker", "run",
            "--rm",  # Удалять контейнер после завершения
            "-v", f"{str(output_dir)}:{docker_project_path}",  # Корень проекта ODM
            "-v", f"{str(image_dir)}:{docker_images_path}",  # Входные изображения
            self.docker_image,
            # Параметры ODM
            "--min-num-features", str(min_num_features),
            "--feature-quality", feature_quality,
            "--project-path", docker_project_path,
            docker_dataset_name,
        ]
        
        self.log_info(f"Запуск ODM для обработки {len(list(image_dir.glob('*.*')))} фотографий...")
        self.log_info("Это может занять значительное время (30+ минут для больших наборов)...")
        
        try:
            result = subprocess.run(
                docker_command,
                capture_output=True,
                text=True,
                check=False,
            )

            self.last_output = result.stdout
            self.last_error = result.stderr

            if result.returncode != 0:
                self.log_error(f"ODM завершился с ошибкой (код {result.returncode})")
                if result.stderr:
                    self.log_error(f"STDERR: {result.stderr[:1200]}")
                elif result.stdout:
                    self.log_error(f"STDOUT: {result.stdout[:1200]}")
                return False

            self.log_success("ODM обработка завершена успешно")
            
            # Ищем выходной файл LAZ или PLY
            output_files = list(output_dir.glob("**/*.laz")) + list(output_dir.glob("**/*.las"))
            if output_files:
                self.log_success(f"Облако точек: {output_files[0]}")
            
            return result.returncode == 0
            
        except Exception as e:
            self.log_error(f"Ошибка при выполнении ODM: {e}")
            return False
    
    def stop_container(self) -> bool:
        """Останавливает работающий контейнер ODM."""
        try:
            result = subprocess.run(
                ["docker", "kill", self.container_name],
                capture_output=True,
                timeout=10
            )
            
            if result.returncode == 0:
                self.log_success(f"Контейнер {self.container_name} остановлен")
                return True
            else:
                self.log_info(f"Контейнер {self.container_name} не найден или уже остановлен")
                return True
                
        except Exception as e:
            self.log_error(f"Ошибка при остановке контейнера: {e}")
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """Получает статус контейнера ODM."""
        try:
            result = subprocess.run(
                ["docker", "ps", "--filter", f"name={self.container_name}", "--format", "json"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout)
                return {
                    'running': True,
                    'container_id': data.get('ID'),
                    'status': data.get('Status'),
                }
            else:
                return {'running': False}
                
        except Exception as e:
            self.log_error(f"Ошибка при получении статуса: {e}")
            return {'error': str(e)}
