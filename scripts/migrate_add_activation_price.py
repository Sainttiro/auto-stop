#!/usr/bin/env python3
"""
Миграция для добавления полей цены активации в таблицы global_settings и instrument_settings
"""

import asyncio
import sqlite3
import os
import sys
from pathlib import Path

# Добавляем корневую директорию проекта в sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.logger import get_logger

logger = get_logger("migration")

# SQL для добавления колонок
ADD_COLUMNS_SQL = """
-- Добавление полей в global_settings
ALTER TABLE global_settings ADD COLUMN sl_activation_pct FLOAT NULL;
ALTER TABLE global_settings ADD COLUMN tp_activation_pct FLOAT NULL;

-- Добавление полей в instrument_settings
ALTER TABLE instrument_settings ADD COLUMN sl_activation_pct FLOAT NULL;
ALTER TABLE instrument_settings ADD COLUMN tp_activation_pct FLOAT NULL;
"""

async def run_migration(db_path):
    """
    Выполнение миграции
    
    Args:
        db_path: Путь к файлу БД
    """
    logger.info(f"Запуск миграции для добавления полей цены активации в БД: {db_path}")
    
    try:
        # Подключение к БД
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Проверка существования колонок перед добавлением
        cursor.execute("PRAGMA table_info(global_settings)")
        global_columns = [col[1] for col in cursor.fetchall()]
        
        cursor.execute("PRAGMA table_info(instrument_settings)")
        instrument_columns = [col[1] for col in cursor.fetchall()]
        
        # Добавление колонок, если они еще не существуют
        if "sl_activation_pct" not in global_columns:
            logger.info("Добавление sl_activation_pct в global_settings")
            cursor.execute("ALTER TABLE global_settings ADD COLUMN sl_activation_pct FLOAT NULL")
        else:
            logger.info("Колонка sl_activation_pct уже существует в global_settings")
        
        if "tp_activation_pct" not in global_columns:
            logger.info("Добавление tp_activation_pct в global_settings")
            cursor.execute("ALTER TABLE global_settings ADD COLUMN tp_activation_pct FLOAT NULL")
        else:
            logger.info("Колонка tp_activation_pct уже существует в global_settings")
        
        if "sl_activation_pct" not in instrument_columns:
            logger.info("Добавление sl_activation_pct в instrument_settings")
            cursor.execute("ALTER TABLE instrument_settings ADD COLUMN sl_activation_pct FLOAT NULL")
        else:
            logger.info("Колонка sl_activation_pct уже существует в instrument_settings")
        
        if "tp_activation_pct" not in instrument_columns:
            logger.info("Добавление tp_activation_pct в instrument_settings")
            cursor.execute("ALTER TABLE instrument_settings ADD COLUMN tp_activation_pct FLOAT NULL")
        else:
            logger.info("Колонка tp_activation_pct уже существует в instrument_settings")
        
        # Сохранение изменений
        conn.commit()
        conn.close()
        
        logger.info("Миграция успешно выполнена")
        return True
    except Exception as e:
        logger.error(f"Ошибка при выполнении миграции: {e}")
        return False

async def main():
    """
    Точка входа
    """
    # Определение пути к БД
    db_path = os.environ.get("DB_PATH", "data/auto_stop.db")
    
    # Проверка существования файла БД
    if not os.path.exists(db_path):
        logger.error(f"Файл БД не найден: {db_path}")
        return False
    
    # Запуск миграции
    success = await run_migration(db_path)
    
    if success:
        logger.info("Миграция успешно завершена")
    else:
        logger.error("Миграция завершилась с ошибками")

if __name__ == "__main__":
    asyncio.run(main())
