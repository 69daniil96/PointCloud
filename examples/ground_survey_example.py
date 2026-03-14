"""
Пример: Обработка изображений наземной съемки с использованием pipeline COLMAP.

Этот скрипт показывает, как обработать изображения наземной съемки
с использованием pipeline COLMAP.
"""

from pathlib import Path
from src.core import Logger, get_logger
from src.pipelines import GroundPipeline


def main():
    """Основная функция примера."""
    # Инициализируем логирование
    Logger.setup(
        'example',
        level='INFO',
        log_file='./data/logs/example_ground.log'
    )
    logger = get_logger('example')
    
    logger.info("Пример обработки наземной съемки")
    logger.info("=" * 70)
    
    # Определяем пути
    image_dir = Path('./data/input/ground')
    output_dir = Path('./data/output/ground_example')
    
    # Проверяем наличие изображений
    if not image_dir.exists():
        logger.error(f"Папка с изображениями не найдена: {image_dir}")
        logger.info(f"Пожалуйста, поместите изображения наземной съемки в: {image_dir}")
        return False
    
    images = list(image_dir.glob('*.jpg')) + list(image_dir.glob('*.png'))
    if not images:
        logger.error(f"Не найдено изображений в {image_dir}")
        return False
    
    logger.info(f"Найдено {len(images)} изображений в {image_dir}")
    
    # Создаем pipeline
    pipeline = GroundPipeline(output_dir)
    
    # Выполняем pipeline
    logger.info("Запуск обработки COLMAP...")
    success = pipeline.execute(
        image_dir=image_dir,
        visualize=True,  # Показать визуализацию облака точек
        save_intermediate=True  # Сохранить промежуточные файлы
    )
    
    if success:
        logger.info("✓ Pipeline успешно завершен!")
        logger.info(f"Результаты сохранены в: {pipeline.output_dir}")
        
        # Выводим статистику
        report = pipeline.get_report()
        logger.info(f"Общее время обработки: {report['total_time']:.2f} секунд")
        
        # Список выходных файлов
        logger.info("\nВыходные файлы:")
        for f in output_dir.glob('**/*.ply'):
            logger.info(f"  - {f.relative_to(output_dir)}")
    else:
        logger.error("✗ Pipeline завершился с ошибкой")
        return False
    
    return True


if __name__ == '__main__':
    main()
