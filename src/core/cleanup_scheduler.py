"""
Планировщик очистки старых данных
"""
import asyncio
from datetime import datetime, time, timedelta
from typing import Optional

from src.storage.database import Database
from src.core.position_manager import PositionManager
from src.utils.logger import get_logger

logger = get_logger("core.cleanup_scheduler")


class CleanupScheduler:
    """
    Планировщик автоматической очистки старых данных
    
    Выполняет очистку старых позиций каждую ночь в 00:01.
    Удаляет позиции, которые не обновлялись более 24 часов.
    """
    
    def __init__(self, position_manager: PositionManager, database: Database):
        """
        Инициализация планировщика
        
        Args:
            position_manager: Менеджер позиций
            database: Объект для работы с базой данных
        """
        self.position_manager = position_manager
        self.db = database
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self, account_id: str) -> None:
        """
        Запуск планировщика
        
        Args:
            account_id: ID счета для очистки позиций
        """
        if self._running:
            logger.warning("Планировщик очистки уже запущен")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run_scheduler(account_id))
        logger.info("Планировщик очистки старых позиций запущен (время очистки: 00:01)")
    
    async def stop(self) -> None:
        """
        Остановка планировщика
        """
        if not self._running:
            logger.warning("Планировщик очистки не запущен")
            return
        
        logger.info("Останавливаем планировщик очистки...")
        self._running = False
        
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        
        self._task = None
        logger.info("Планировщик очистки остановлен")
    
    async def _run_scheduler(self, account_id: str) -> None:
        """
        Основной цикл планировщика
        
        Args:
            account_id: ID счета для очистки позиций
        """
        while self._running:
            try:
                # Вычисляем время до следующей очистки (00:01)
                now = datetime.now()
                target_time = datetime.combine(
                    now.date() + timedelta(days=1),
                    time(0, 1)  # 00:01
                )
                
                # Если сейчас уже после 00:01, очистка будет завтра
                if now.time() < time(0, 1):
                    target_time = datetime.combine(now.date(), time(0, 1))
                
                sleep_seconds = (target_time - now).total_seconds()
                
                logger.info(
                    f"Следующая очистка старых позиций: {target_time.strftime('%Y-%m-%d %H:%M:%S')} "
                    f"(через {sleep_seconds/3600:.1f} часов)"
                )
                
                # Ждем до целевого времени
                await asyncio.sleep(sleep_seconds)
                
                # Выполняем очистку
                await self._cleanup_old_positions(account_id)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка в планировщике очистки: {e}", exc_info=True)
                # Логируем событие
                await self.db.log_event(
                    event_type="CLEANUP_ERROR",
                    account_id=account_id,
                    description=f"Ошибка в планировщике очистки: {str(e)}",
                    details={"error": str(e)}
                )
                # Ждем 1 час перед повторной попыткой
                await asyncio.sleep(3600)
    
    async def _cleanup_old_positions(self, account_id: str) -> None:
        """
        Очистка старых позиций
        
        Удаляет позиции, которые:
        1. Не обновлялись более 24 часов
        2. Отсутствуют у брокера (опционально)
        
        Args:
            account_id: ID счета
        """
        try:
            logger.info("🧹 Начинаем очистку старых позиций...")
            
            # Получаем все позиции из БД для данного счета
            positions = await self.db.get_all_positions(account_id)
            
            if not positions:
                logger.info("Нет позиций для очистки")
                return
            
            cleaned_count = 0
            current_time = datetime.utcnow()
            
            for position in positions:
                # Проверяем время последнего обновления
                time_since_update = current_time - position.updated_at
                
                # Если позиция не обновлялась более 24 часов
                if time_since_update > timedelta(hours=24):
                    logger.warning(
                        f"⚠️ Позиция {position.ticker} не обновлялась {time_since_update}. "
                        f"Удаляем из БД."
                    )
                    
                    try:
                        # Удаляем позицию
                        await self.position_manager.close_position(position.id)
                        cleaned_count += 1
                        
                        # Логируем событие
                        await self.db.log_event(
                            event_type="OLD_POSITION_CLEANED",
                            account_id=account_id,
                            figi=position.figi,
                            ticker=position.ticker,
                            description=(
                                f"Удалена старая позиция {position.ticker} "
                                f"(не обновлялась {time_since_update})"
                            ),
                            details={
                                "position_id": position.id,
                                "time_since_update_hours": time_since_update.total_seconds() / 3600,
                                "quantity": position.quantity,
                                "average_price": position.average_price,
                                "direction": position.direction
                            }
                        )
                    except Exception as e:
                        logger.error(
                            f"Ошибка при удалении старой позиции {position.ticker} (id={position.id}): {e}",
                            exc_info=True
                        )
                        # Продолжаем обработку других позиций
                        continue
            
            logger.info(f"✅ Очистка завершена. Удалено позиций: {cleaned_count}")
            
            # Логируем итоговое событие
            await self.db.log_event(
                event_type="CLEANUP_COMPLETED",
                account_id=account_id,
                description=f"Очистка старых позиций завершена. Удалено: {cleaned_count}",
                details={
                    "total_positions": len(positions),
                    "cleaned_count": cleaned_count,
                    "cleanup_time": current_time.isoformat()
                }
            )
            
        except Exception as e:
            logger.error(f"Ошибка при очистке старых позиций: {e}", exc_info=True)
            # Логируем событие
            await self.db.log_event(
                event_type="CLEANUP_ERROR",
                account_id=account_id,
                description=f"Ошибка при очистке старых позиций: {str(e)}",
                details={"error": str(e)}
            )
