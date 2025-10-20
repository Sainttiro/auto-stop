#!/usr/bin/env python3
"""
Скрипт миграции существующего токена в таблицу accounts
"""
import asyncio
import os
import sys
from pathlib import Path

# Добавить корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.storage.database import Database
from src.utils.logger import get_logger
from dotenv import load_dotenv

logger = get_logger("migration")


async def migrate():
    """Миграция текущего токена в таблицу accounts"""
    
    # Загрузить переменные окружения
    load_dotenv()
    
    db = Database()
    await db.create_tables()
    
    # Проверить, есть ли уже аккаунты
    accounts = await db.get_all_accounts()
    
    if accounts:
        logger.info(f"✅ В БД уже есть {len(accounts)} аккаунт(ов). Миграция не требуется.")
        logger.info("Список существующих аккаунтов:")
        for acc in accounts:
            status = "🟢 активный" if acc.is_active else "⚪ неактивный"
            logger.info(f"  - {acc.name} ({status}): {acc.account_id}")
        return
    
    # Загрузить токен из .env
    token = os.getenv("TINKOFF_TOKEN")
    if not token:
        logger.error("❌ TINKOFF_TOKEN не найден в переменных окружения")
        logger.info("Убедитесь, что файл .env существует и содержит TINKOFF_TOKEN")
        return
    
    # Получить account_id из .env (если есть)
    account_id = os.getenv("TINKOFF_ACCOUNT_ID", "auto")
    
    # Создать первый аккаунт
    try:
        logger.info("Создаю первый аккаунт 'main' из текущего токена...")
        
        account = await db.add_account(
            name="main",
            token=token,
            account_id=account_id,
            description="Основной счет (мигрирован автоматически)"
        )
        
        # Пометить как активный
        await db.switch_account("main")
        
        logger.info("=" * 60)
        logger.info("✅ Миграция завершена успешно!")
        logger.info("=" * 60)
        logger.info(f"Создан аккаунт: {account.name}")
        logger.info(f"ID в БД: {account.id}")
        logger.info(f"Account ID: {account.account_id}")
        logger.info(f"Активный: {account.is_active}")
        logger.info(f"Описание: {account.description}")
        logger.info("=" * 60)
        logger.info("")
        logger.info("Теперь вы можете:")
        logger.info("  1. Добавить дополнительные аккаунты через Telegram бот:")
        logger.info("     /add_account <название> <токен> <account_id> [описание]")
        logger.info("")
        logger.info("  2. Переключаться между аккаунтами без перезапуска:")
        logger.info("     /switch_account <название>")
        logger.info("")
        logger.info("  3. Просмотреть все аккаунты:")
        logger.info("     /accounts")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"❌ Ошибка при миграции: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("=" * 60)
    print("Миграция к мультиаккаунтам")
    print("=" * 60)
    print("")
    
    asyncio.run(migrate())
