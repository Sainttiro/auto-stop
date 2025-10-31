"""
Класс для отмены ордеров
"""

from src.storage.models import Order
from src.core.utils.order_logger import log_order_cancelled
from src.utils.logger import get_logger
from src.core.orders.base_placer import BaseOrderPlacer

logger = get_logger("core.orders.order_canceller")


class OrderCanceller(BaseOrderPlacer):
    """
    Класс для отмены ордеров
    """
    
    async def cancel_order(self, order: Order) -> bool:
        """
        Отмена ордера
        
        Args:
            order: Ордер для отмены
            
        Returns:
            bool: True, если ордер успешно отменен
        """
        try:
            # Отменяем ордер через API
            if order.order_type == "STOP":
                await self.api_client.services.stop_orders.cancel_stop_order(
                    account_id=order.account_id,
                    stop_order_id=order.order_id
                )
            else:
                await self.api_client.services.orders.cancel_order(
                    account_id=order.account_id,
                    order_id=order.order_id
                )
            
            # Обновляем статус ордера в БД
            order.status = "CANCELLED"
            await self.db.update(order)
            
            # Логируем событие
            await log_order_cancelled(
                db=self.db,
                order=order
            )
            
            logger.info(f"Ордер {order.order_id} ({order.order_purpose}) отменен")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при отмене ордера {order.order_id}: {e}")
            
            # Логируем ошибку
            await self._log_order_error(
                account_id=order.account_id,
                figi=order.figi,
                ticker=None,
                error=e,
                order_type="CANCEL",
                order_id=order.order_id
            )
            
            return False
    
    async def cancel_position_orders(self, position_id: int) -> int:
        """
        Отмена всех ордеров для позиции
        
        Args:
            position_id: ID позиции
            
        Returns:
            int: Количество отмененных ордеров
        """
        # Получаем все активные ордера для позиции
        orders = await self.db.get_active_orders_by_position(position_id)
        
        if not orders:
            logger.debug(f"Нет активных ордеров для позиции {position_id}")
            return 0
        
        # Отменяем каждый ордер
        cancelled_count = 0
        for order in orders:
            if await self.cancel_order(order):
                cancelled_count += 1
        
        logger.info(f"Отменено {cancelled_count} из {len(orders)} ордеров для позиции {position_id}")
        return cancelled_count
    
    async def cancel_account_orders(self, account_id: str) -> int:
        """
        Отмена всех ордеров для аккаунта
        
        Args:
            account_id: ID аккаунта
            
        Returns:
            int: Количество отмененных ордеров
        """
        # Получаем все активные ордера для аккаунта
        orders = await self.db.get_active_orders_by_account(account_id)
        
        if not orders:
            logger.debug(f"Нет активных ордеров для аккаунта {account_id}")
            return 0
        
        # Отменяем каждый ордер
        cancelled_count = 0
        for order in orders:
            if await self.cancel_order(order):
                cancelled_count += 1
        
        logger.info(f"Отменено {cancelled_count} из {len(orders)} ордеров для аккаунта {account_id}")
        return cancelled_count
