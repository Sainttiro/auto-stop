import os
import sys
from pathlib import Path
from loguru import logger

from src.config.settings import LoggingSettings


def setup_logger(config: LoggingSettings) -> None:
    """
    Настройка логирования с использованием loguru
    
    Args:
        config: Настройки логирования из конфигурации
    """
    # Создаем директорию для логов, если она не существует
    log_dir = Path(config.file).parent
    os.makedirs(log_dir, exist_ok=True)
    
    # Удаляем стандартный обработчик
    logger.remove()
    
    # Добавляем обработчик для вывода в консоль
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=config.level,
        colorize=True
    )
    
    # Добавляем обработчик для записи в файл с ротацией
    logger.add(
        config.file,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level=config.level,
        rotation=config.max_bytes,
        retention=config.backup_count,
        compression="zip"
    )
    
    logger.info(f"Логирование настроено. Уровень: {config.level}, файл: {config.file}")


def get_logger(name: str):
    """
    Получить логгер для конкретного модуля
    
    Args:
        name: Имя модуля
        
    Returns:
        Настроенный логгер
    """
    return logger.bind(name=name)
