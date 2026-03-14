"""
Пример: Обработка изображений дронной съемки с использованием pipeline ODM.

Этот скрипт показывает, как обработать изображения дронной съемки
с использованием pipeline ODM (OpenDroneMap).

Требуемия:
- Docker Desktop установлен и запущен
- Docker образ ODM (будет загружен автоматически, если необходимо)
"""

from pathlib import Path
from src.core import Logger, get_logger
from src.pipelines import DronePipeline


def main():
    """Основная функция примера."""
    # Инициализируем логирование
    Logger.setup(
        'example',
        level='INFO',
        log_file='./data/logs/example_drone.log'
    )
    logger = get_logger('example')
    
    logger.info("Пример обработки дронной съемки")
    logger.info("=" * 70)
    
    # Определяем пути
    image_dir = Path('./data/input/drone')
    output_dir = Path('./data/output/drone_example')
    
    # Проверяем наличие изображений
    if not image_dir.exists():
        logger.error(f"Папка с изображениями не найдена: {image_dir}")
        logger.info(f"Пожалуйста, поместите изображения дронной съемки в: {image_dir}")
        return False
    
    images = list(image_dir.glob('*.jpg')) + list(image_dir.glob('*.png'))
    if not images:
        logger.error(f"Не найдено изображений в {image_dir}")
        return False
    
    logger.info(f"Найдено {len(images)} изображений в {image_dir}")
    
    # Создаем pipeline
    pipeline = DronePipeline(output_dir)
    
    # Выполняем pipeline
    logger.info("Запуск обработки ODM...")
    logger.info("⚠ Обработка может занять 30+ минут для больших наборов данных")
    
    success = pipeline.execute(
        image_dir=image_dir,
        visualize=True,  # Показать визуализацию облака точек
        save_intermediate=True,  # Сохранить промежуточные файлы
        pull_docker_image=True  # Загрузить образ ODM, если необходимо
    )
    
    if success:
        logger.info("✓ Pipeline успешно завершен!")
        logger.info(f"Результаты сохранены в: {pipeline.output_dir}")
        
        # Выводим статистику
        report = pipeline.get_report()
        logger.info(f"Общее время обработки: {report['total_time']:.2f} секунд")
        logger.info(f"Общее время обработки: {report['total_time'] / 3600:.2f} часов")
        
        # Список выходных файлов
        logger.info("\nВыходные файлы:")
        for f in output_dir.glob('**/*.ply') + output_dir.glob('**/*.las'):
            logger.info(f"  - {f.relative_to(output_dir)}")
    else:
        logger.error("✗ Pipeline завершился с ошибкой")
        return False
    
    return True


if __name__ == '__main__':
    main()
