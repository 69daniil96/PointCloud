"""
CLI интерфейс для PointCloud Processing Pipeline.
"""

import click
from pathlib import Path
import sys
from importlib.metadata import version as package_version, PackageNotFoundError

from src.core import Logger, get_config, get_logger, get_path_manager
from src.pipelines import GroundPipeline, DronePipeline


AVAILABLE_LAYERS = [
    'final',
    'ground',
    'vegetation',
    'outliers',
    'no_ground',
    'no_outliers',
]

LAYER_PRESETS = {
    'terrain': ['final', 'ground'],
    'vegetation': ['final', 'vegetation', 'ground'],
    'quality-control': ['final', 'outliers', 'no_ground', 'no_outliers'],
    'all': ['final', 'ground', 'vegetation', 'outliers', 'no_ground', 'no_outliers'],
}


def _parse_layers(layers_option: str):
    """Парсит CSV со слоями визуализации в список."""
    if not layers_option:
        return None

    layers = [layer.strip() for layer in layers_option.split(',') if layer.strip()]
    return layers or None


def _resolve_layers(layers_option: str, layers_preset: str):
    """Определяет итоговый список слоев: custom CSV или preset."""
    selected_layers = _parse_layers(layers_option)
    if selected_layers is None:
        selected_layers = list(LAYER_PRESETS[layers_preset])

    invalid_layers = [layer for layer in selected_layers if layer not in AVAILABLE_LAYERS]
    if invalid_layers:
        valid = ', '.join(AVAILABLE_LAYERS)
        invalid = ', '.join(invalid_layers)
        raise click.BadParameter(
            f"Неизвестные слои: {invalid}. Доступные: {valid}",
            param_hint='--layers'
        )

    return selected_layers


@click.group()
@click.version_option(version='1.0.0')
def cli():
    """
    PointCloud Processing Pipeline v1.0.0
    
    Унифицированный инструмент для обработки данных дронной и наземной фотограмметрии.
    """
    pass


@cli.command()
@click.argument('image_dir', type=click.Path(exists=True))
@click.option(
    '--output-dir',
    type=click.Path(),
    default=None,
    help='Директория для сохранения результатов (по умолчанию: ./data/output/ground)'
)
@click.option(
    '--no-visualization',
    is_flag=True,
    help='Отключить визуализацию облака точек'
)
@click.option(
    '--save-intermediate',
    is_flag=True,
    default=True,
    help='Сохранять промежуточные файлы'
)
@click.option(
    '--layers',
    type=str,
    default=None,
    help=(
        'Явный список слоев для старта визуализации через запятую '
        '(переопределяет --layers-preset): '
        'final, ground, vegetation, outliers, no_ground, no_outliers'
    )
)
@click.option(
    '--layers-preset',
    type=click.Choice(list(LAYER_PRESETS.keys()), case_sensitive=False),
    default='terrain',
    show_default=True,
    help='Пресет слоев визуализации: terrain, vegetation, quality-control, all'
)
def process_ground(image_dir, output_dir, no_visualization, save_intermediate, layers, layers_preset):
    """
    Обработать изображения наземной съемки с использованием COLMAP.
    
    IMAGE_DIR: Путь к папке с изображениями наземной съемки
    """
    # Инициализируем логирование
    Logger.setup(
        'main',
        level='INFO',
        log_file='./data/logs/app.log'
    )
    logger = get_logger('cli')
    
    logger.info("=" * 70)
    logger.info("PointCloud Processing Pipeline - Режим наземной съемки")
    logger.info("=" * 70)
    
    image_dir = Path(image_dir)
    
    # Проверяем что папка содержит изображения
    images = list(image_dir.glob('*.jpg')) + list(image_dir.glob('*.JPG')) + \
             list(image_dir.glob('*.png')) + list(image_dir.glob('*.PNG'))
    
    if not images:
        logger.error(f"[ERROR] Нет изображений в {image_dir}")
        sys.exit(1)
    
    logger.info(f"[OK] Найдено изображений: {len(images)}")
    
    # Инициализируем pipeline
    if output_dir:
        output_dir = Path(output_dir)
    
    pipeline = GroundPipeline(output_dir)
    
    # Выполняем pipeline
    selected_layers = _resolve_layers(layers, layers_preset)
    success = pipeline.execute(
        image_dir=image_dir,
        visualize=not no_visualization,
        visualize_layers=selected_layers,
        save_intermediate=save_intermediate
    )
    
    if success:
        logger.info("\n[OK] Конвейер обработки завершен успешно!")
        logger.info(f"Результаты сохранены в: {pipeline.output_dir}")
        sys.exit(0)
    else:
        logger.error("\n[ERROR] Конвейер обработки завершился с ошибкой")
        sys.exit(1)


@cli.command()
@click.argument('image_dir', type=click.Path(exists=True))
@click.option(
    '--output-dir',
    type=click.Path(),
    default=None,
    help='Директория для сохранения результатов (по умолчанию: ./data/output/drone)'
)
@click.option(
    '--no-visualization',
    is_flag=True,
    help='Отключить визуализацию облака точек'
)
@click.option(
    '--save-intermediate',
    is_flag=True,
    default=True,
    help='Сохранять промежуточные файлы'
)
@click.option(
    '--pull-docker-image',
    is_flag=True,
    help='Загрузить Docker образ ODM, если его нет'
)
@click.option(
    '--layers',
    type=str,
    default=None,
    help=(
        'Явный список слоев для старта визуализации через запятую '
        '(переопределяет --layers-preset): '
        'final, ground, vegetation, outliers, no_ground, no_outliers'
    )
)
@click.option(
    '--layers-preset',
    type=click.Choice(list(LAYER_PRESETS.keys()), case_sensitive=False),
    default='terrain',
    show_default=True,
    help='Пресет слоев визуализации: terrain, vegetation, quality-control, all'
)
def process_drone(image_dir, output_dir, no_visualization, save_intermediate, pull_docker_image, layers, layers_preset):
    """
    Обработать изображения дронной съемки с использованием ODM.
    
    IMAGE_DIR: Путь к папке с изображениями дронной съемки
    """
    # Инициализируем логирование
    Logger.setup(
        'main',
        level='INFO',
        log_file='./data/logs/app.log'
    )
    logger = get_logger('cli')
    
    logger.info("=" * 70)
    logger.info("PointCloud Processing Pipeline - Режим дронной съемки")
    logger.info("=" * 70)
    
    image_dir = Path(image_dir)
    
    # Проверяем что папка содержит изображения
    images = list(image_dir.glob('*.jpg')) + list(image_dir.glob('*.JPG')) + \
             list(image_dir.glob('*.png')) + list(image_dir.glob('*.PNG'))
    
    if not images:
        logger.error(f"[ERROR] Нет изображений в {image_dir}")
        sys.exit(1)
    
    logger.info(f"[OK] Найдено изображений: {len(images)}")
    
    # Инициализируем pipeline
    if output_dir:
        output_dir = Path(output_dir)
    
    pipeline = DronePipeline(output_dir)
    
    # Выполняем pipeline
    selected_layers = _resolve_layers(layers, layers_preset)
    success = pipeline.execute(
        image_dir=image_dir,
        visualize=not no_visualization,
        visualize_layers=selected_layers,
        save_intermediate=save_intermediate,
        pull_docker_image=pull_docker_image
    )
    
    if success:
        logger.info("\n[OK] Конвейер обработки завершен успешно!")
        logger.info(f"Результаты сохранены в: {pipeline.output_dir}")
        sys.exit(0)
    else:
        logger.error("\n[ERROR] Конвейер обработки завершился с ошибкой")
        sys.exit(1)


@cli.command()
def check_dependencies():
    """
    Проверить, установлены ли все необходимые зависимости.
    """
    Logger.setup('main', level='INFO')
    logger = get_logger('cli')
    
    logger.info("=" * 70)
    logger.info("Проверка зависимостей")
    logger.info("=" * 70)
    
    dependencies = {
        'NumPy': lambda: __import__('numpy'),
        'OpenCV': lambda: __import__('cv2'),
        'Open3D': lambda: __import__('open3d'),
        'PDAL': lambda: __import__('pdal'),
        'LASpy': lambda: __import__('laspy'),
        'YAML': lambda: __import__('yaml'),
        'Click': lambda: __import__('click'),
    }
    
    # Проверяем Python зависимости
    logger.info("\nPython пакеты:")
    all_ok = True
    for name, import_func in dependencies.items():
        try:
            module = import_func()
            if name == 'Click':
                try:
                    version = package_version('click')
                except PackageNotFoundError:
                    version = getattr(module, '__version__', 'unknown')
            else:
                version = getattr(module, '__version__', 'unknown')
            logger.info(f"  [OK] {name:20} v{version}")
        except ImportError:
            logger.warning(f"  [ERROR] {name:20} НЕ УСТАНОВЛЕН")
            all_ok = False
    
    # Проверяем инструменты
    logger.info("\nВнешние инструменты:")
    
    from src.adapters import ColmapRunner, ODMRunner
    
    colmap = ColmapRunner()
    if colmap.is_available():
        logger.info(f"  [OK] COLMAP                {colmap.colmap_exe}")
    else:
        logger.warning("  [ERROR] COLMAP                НЕ НАЙДЕН")
        all_ok = False
    
    odm = ODMRunner()
    if odm.is_available():
        logger.info(f"  [OK] ODM (Docker)          Доступен")
    else:
        logger.warning("  [ERROR] ODM (Docker)          НЕДОСТУПЕН")
    
    # Итоговый результат
    logger.info("\n" + "=" * 70)
    if all_ok:
        logger.info("[OK] Все необходимые зависимости установлены!")
    else:
        logger.warning("[WARN] Некоторые зависимости отсутствуют. Пожалуйста, установите их.")
    logger.info("=" * 70)


@cli.command()
def show_config():
    """
    Отобразить текущую конфигурацию.
    """
    Logger.setup('main', level='INFO')
    logger = get_logger('cli')
    
    config = get_config()
    
    logger.info("=" * 70)
    logger.info("Текущая конфигурация")
    logger.info("=" * 70)
    
    import json
    config_dict = config.to_dict()
    logger.info(json.dumps(config_dict, indent=2, ensure_ascii=False))


@cli.command()
def list_tools():
    """
    Список доступных инструментов и их статус.
    """
    Logger.setup('main', level='INFO')
    logger = get_logger('cli')
    
    logger.info("=" * 70)
    logger.info("Доступные инструменты")
    logger.info("=" * 70)
    
    from src.adapters import ColmapRunner, ODMRunner, PDALProcessor, Open3DProcessor
    
    tools = {
        'COLMAP': ColmapRunner(),
        'ODM': ODMRunner(),
        'PDAL': PDALProcessor(),
        'Open3D': Open3DProcessor(),
    }
    
    for name, tool in tools.items():
        status = "[OK] Доступен" if tool.is_available() else "[ERROR] Недоступен"
        logger.info(f"{name:20} {status}")


if __name__ == '__main__':
    cli()
