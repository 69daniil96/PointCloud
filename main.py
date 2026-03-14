"""
PointCloud Processing Pipeline - Точка входа

Этот модуль инициализирует и демонстрирует конвейер обработки облаков точек.
"""

import sys
from pathlib import Path

# Добавляем src директорию в путь
sys.path.insert(0, str(Path(__file__).parent))

from src.core import Logger, get_config, get_logger
from src.ui.cli import cli
from src.adapters import ColmapRunner, ODMRunner, PDALProcessor, Open3DProcessor


def check_dependencies():
    """Проверка установки всех необходимых библиотек."""
    from src.ui.cli import check_dependencies as check_cmd
    from click.testing import CliRunner
    
    runner = CliRunner()
    result = runner.invoke(check_cmd)
    print(result.output)


def main():
    """Главная функция."""
    # Инициализируем логирование
    Logger.setup(
        'main',
        level='INFO',
        log_file='./data/logs/app.log'
    )
    logger = get_logger('main')
    
    logger.info("=" * 70)
    logger.info("PointCloud Processing Pipeline v1.0.0")
    logger.info("=" * 70)
    
    # Используем CLI интерфейс
    cli()


if __name__ == "__main__":
    main()